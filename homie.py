import robust
import machine
import ubinascii
import time

VERSION = "3.0"

NAME_SEND_INTERVAL = 50
log = True

def publish(mqtt, topic, value, qos=1, retained=True):
    if isinstance(topic, list):
        joint_topic = "/".join(topic)
    else:
        joint_topic = topic
    if log:
        print(joint_topic, value)
    mqtt.publish(joint_topic, value, retained, qos)
    return joint_topic


publish_wait_queue = []

class HomieDevice:
    base = "homie"
    BROADCAST = "$broadcast"

    def __init__(self, mqtt, device_id, nodes, nice_device_name, broadcast_cb=None):
        self.mqtt = mqtt
        self.nodes = nodes
        self.nice_device_name = nice_device_name
        self.user_cb = None
        self.broadcast_cb = broadcast_cb
        self.mqtt.set_callback(self.subscribe_cb)

        base_list = [self.base, device_id.decode("ascii"), "$state" ]
        state_topic = "/".join(base_list)
        self.mqtt.set_last_will(state_topic, "lost", True, 1)

        self.mqtt.connect(clean_session=True)
        self.mqtt.disconnect()
        self.mqtt.connect(clean_session=False)

        base_list[-1] = "$homie"
        publish(self.mqtt, base_list, VERSION)

        base_list[-1] = "$name"
        self.name_topic = publish(self.mqtt, base_list, nice_device_name)
        self.last_name_sent = time.time()

        publish(self.mqtt, state_topic, "init")

        base_list[-1] = "$nodes"
        publish(self.mqtt, base_list, ",".join([node.node_id for node in self.nodes]))

        settable = False
        for node in nodes:
            settable |= node.expose(self.mqtt, list(base_list))
        if settable:
            base_list[-1] = "+"
            base_list.append("+")
            base_list.append("set")
            mqtt.subscribe("/".join(base_list))

        if broadcast_cb:
            mqtt.subscribe("/".join([self.base, self.BROADCAST, '#']), 1)

        publish(self.mqtt, state_topic, "ready")

    def set_user_cb(self, cb):
        self.user_cb = cb

    def subscribe_cb(self, topic, content, retain):
        topic_split = topic.decode("ascii").split("/")
        value = content.decode("utf-8")
        found = False
        if len(topic_split) == 5 and topic_split[4] == "set":
            for node in self.nodes:
                found = node.action_set(topic_split, value)
                if found:
                    break;
        if not found and self.broadcast_cb and topic_split[1]=="$broadcast":
            self.broadcast_cb(topic, content, retain)
            found = True
        if not found and self.user_cb:
            self.user_cb(topic, content)

    def main(self):
        self.mqtt.check_msg()
        while len(publish_wait_queue):
            prop, value = publish_wait_queue.pop()
            prop.send_value(value)
        now = time.time()
        if now - self.last_name_sent > NAME_SEND_INTERVAL:
            publish(self.mqtt, self.name_topic, self.nice_device_name, 0, False)
            self.last_name_sent = now


class Node:
    def __init__(self, node_id, name, properties):
        self.node_id = node_id
        self.name = name
        self.properties = properties

    def expose(self, mqtt, base_list):
        self.mqtt = mqtt

        base_list[-1] = self.node_id

        base_list.append("$name")
        publish(self.mqtt, base_list, self.name)

        base_list[-1] = "$properties"
        publish( self.mqtt, base_list, ",".join([prop.property_id for prop in self.properties]))

        settable = False
        for prop in self.properties:
            settable |= prop.expose(self.mqtt, list(base_list))
        return settable

    def action_set(self, topic_split, value):
        if topic_split[2] == self.node_id:
            for prop in self.properties:
                if prop.call_cb(topic_split, value):
                    return True
        return False

class Property:
    def __init__(self, property_id, name, type, unit, format, init_value, value_set_cb=None, retained=True):
        self.property_id = property_id
        self.name = name
        self.type = type
        self.unit = unit
        self.format = format
        self.init_value = str(init_value)
        self.retained = retained
        self.value_set_cb = value_set_cb

    def expose(self, mqtt, base_list):
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

        if not self.retained:
            base_list[-1] = "$retained"
            publish( self.mqtt, base_list, "false")

        if self.value_set_cb:
            base_list[-1] = "$settable"
            publish( self.mqtt, base_list, "true")
            return True
        return False

    def send_value(self, value):
        publish(self.mqtt, self.value_topic, value, 0, self.retained)

    def call_cb(self, topic_split, value):
        if topic_split[3] == self.property_id and self.value_set_cb:
            if self.value_set_cb(topic_split, value):
                publish_wait_queue.append((self, value))
            return True
        else:
            return False


if __name__ == "__main__":
    def my_cb(topic_split, value):
        print ("custom cb", topic_split[-1], value)

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
