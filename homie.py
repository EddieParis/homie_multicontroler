import robust
import machine
import ubinascii
import time

VERSION = "3.0"

TIME_SEND_INTERVAL = 50*1000
log = True

def publish(mqtt, topic, value):
    if isinstance(topic, list):
        joint_topic = "/".join(topic)
    else:
        joint_topic = topic
    if log:
        print(joint_topic, value)
    mqtt.publish(joint_topic, value, True, 1)
    return joint_topic


publish_wait_queue = []

class HomieDevice:
    base = "homie"

    def __init__(self, mqtt, device_id, nodes, nice_device_name):
        self.nodes = nodes
        self.nice_device_name = nice_device_name
        self.mqtt = mqtt
        self.mqtt.set_callback(self.subscribe_cb)

        base_list = [self.base, device_id.decode("ascii"), "" ]

        base_list[-1] = "$homie"
        publish(self.mqtt, base_list, VERSION)

        base_list[-1] = "$name"
        self.name_topic = publish(self.mqtt, base_list, nice_device_name)
        self.last_name_sent = time.ticks_ms()

        base_list[-1] = "$state"
        state_topic = publish(self.mqtt, base_list, "init")
        self.mqtt.set_last_will(state_topic, "lost", True, 1)

        base_list[-1] = "$nodes"
        publish(self.mqtt, base_list, ",".join([node.node_id for node in self.nodes]))

        for node in nodes:
            node.publish(self.mqtt, list(base_list))

        publish(self.mqtt, state_topic, "ready")

    def subscribe_cb(self, topic, content):
        topic_split = topic.decode("ascii").split("/")
        value = content.decode("utf-8")
        node_iter = iter(self.nodes)
        found = False
        while not found:
            try:
                node = next(node_iter)
            except StopIteration:
                return False
            found = node.action_set(topic_split, value)

    def main(self):
        self.mqtt.check_msg()
        while len(publish_wait_queue):
            prop, value = publish_wait_queue.pop()
            prop.send_value(value)
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_name_sent) > TIME_SEND_INTERVAL:
            publish(self.mqtt, self.name_topic, self.nice_device_name)
            self.last_name_sent = now


class Node:
    def __init__(self, node_id, name, properties):
        self.node_id = node_id
        self.name = name
        self.properties = properties

    def publish(self, mqtt, base_list):
        self.mqtt = mqtt

        base_list[-1] = self.node_id

        base_list.append("$name")
        publish(self.mqtt, base_list, self.name)

        base_list[-1] = "$properties"
        publish( self.mqtt, base_list, ",".join([prop.property_id for prop in self.properties]))

        for prop in self.properties:
            prop.publish(self.mqtt, list(base_list))

    def action_set(self, topic_split, value):
        if topic_split[2] == self.node_id:
            prop_iter = iter(self.properties)
            found = False
            while not found:
                try:
                    prop = next(prop_iter)
                except StopIteration:
                    return False
                found = prop.call_cb(topic_split, value)
        else:
            return False

class Property:
    def __init__(self, property_id, name, type, unit, format, init_value, value_set_cb=None):
    # ~ def __init__(self, property_id, name, type, unit, format, init_value, retained, value_set_cb=None):
        self.property_id = property_id
        self.name = name
        self.type = type
        self.unit = unit
        self.format = format
        self.init_value = str(init_value)
        # ~ self.retained = retained
        self.value_set_cb = value_set_cb

    def publish(self, mqtt, base_list):
        self.mqtt = mqtt

        base_list[-1] = self.property_id
        self.value_topic = publish(self.mqtt, base_list, self.init_value)

        base_list.append("$name")
        publish( self.mqtt, base_list, self.name)

        base_list[-1] = "$datatype"
        publish( self.mqtt, base_list, self.type)

        if self.unit:
            base_list[-1] = "$unit"
            publish( self.mqtt, base_list, self.unit)

        if self.format:
            base_list[-1] = "$format"
            publish( self.mqtt, base_list, self.format)

        # ~ if self.retained:
            # ~ base_list[-1] = "$retained"
            # ~ publish( self.mqtt, base_list, True)

        if self.value_set_cb:
            base_list[-1] = "$settable"
            publish( self.mqtt, base_list, "true")
            base_list[-1] = "set"
            self.mqtt.subscribe("/".join(base_list), 1)

    def send_value(self, value):
        publish(self.mqtt, self.value_topic, value)

    def call_cb(self, topic_split, value):
        if topic_split[3] == self.property_id:
            if self.value_set_cb(topic_split, value):
                publish_wait_queue.append((self, value))
            return True
        else:
            return False

def my_cb(topic_split, value):
    print ("custom cb", topic_split[-1], value)

if __name__ == "__main__":
    MQTT_ID = b"esp32_"+ ubinascii.hexlify(machine.unique_id())

    mqtt = robust.MQTTClient(MQTT_ID, "192.168.2.42")
    mqtt.connect()

    props_color = [ Property("color", "desired color RGB", "color", None, "rgb", "0,0,0", my_cb) ]
    dim_props = [ Property("chan-a", "Dimmer A", "float", None, "0:100", 0, my_cb), Property("chan-b", "Dimmer B", "integer", "%", "0:100", 0, my_cb), Property("chan-c", "Dimmer C", "integer", "%", "0:100", 0, my_cb), Property("chan-d", "Dimmer D", "integer", "%", "0:100", 0, my_cb) ]
    env_props = [ Property("temperature", "Temperature", "float", "°C".encode("utf-8"), None, 0), Property("humidity", "Humidity", "float", "%", "0:100", 0), Property("pressure", "Atmospheric pressure", "float", "mBar", None, 0) ]
    nodes = [ Node("color", "Color leds (on ABC)", props_color), Node("dimmer", "Dimmers channels", dim_props), Node("evironment", "Environment Measures", env_props) ]
    device = HomieDevice( mqtt, ubinascii.hexlify(machine.unique_id()), nodes, "Multicontroler")

    while(True):
        device.mqtt.check_msg()
        time.sleep(.050)
