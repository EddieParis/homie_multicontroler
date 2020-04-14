  # ~ homie / device123 / $homie → 3.0
  # ~ homie / device123 / $name → My device
  # ~ homie / device123 / $state → ready
  # ~ homie / device123 / $nodes → mythermostat

  # ~ homie / device123 / mythermostat / $name → My thermostat
  # ~ homie / device123 / mythermostat / $properties → temperature

  # ~ homie / device123 / mythermostat / temperature → 22
  # ~ homie / device123 / mythermostat / temperature / $name → Temperature
  # ~ homie / device123 / mythermostat / temperature / $unit → °C
  # ~ homie / device123 / mythermostat / temperature / $datatype → integer
  # ~ homie / device123 / mythermostat / temperature / $settable → true
import robust
import machine
import ubinascii
import time

VERSION = "3.0"

MQTT_ID = b"esp32_"+ ubinascii.hexlify(machine.unique_id())

log = True

def publish(mqtt, topic, value):
    joint_topic = "/".join(topic)
    if log:
        print(joint_topic, value)
    mqtt.publish(joint_topic, value, True, 1)

class HomieDevice:
    base = "homie"

    def __init__(self, device_id, nodes, nice_device_name):
        self.nodes = nodes

        self.mqtt = robust.MQTTClient(MQTT_ID, "192.168.2.42")
        self.mqtt.connect()

        self.mqtt.set_callback(self.subscribe_cb)

        base_list = [ self.base, device_id.decode("ascii"), "" ]

        base_list[-1] = "$homie"
        publish( self.mqtt, base_list, VERSION)

        base_list[-1] = "$name"
        publish( self.mqtt, base_list, nice_device_name)

        base_list[-1] = "$state"
        publish( self.mqtt, base_list, "ready")
        self.mqtt.set_last_will("/".join(base_list), "lost", True, 1)

        base_list[-1] = "$nodes"
        publish( self.mqtt, base_list, ",".join([node.node_id for node in self.nodes]))

        for node in nodes:
            node.publish(self.mqtt, list(base_list))

    def subscribe_cb(self, topic, content):
        print ("got message", topic, content)
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
    def __init__(self, property_id, name, type, unit, format, init_value, set_value_cb=None):
        self.property_id = property_id
        self.name = name
        self.type = type
        self.unit = unit
        self.format = format
        self.init_value = str(init_value)
        self.set_value_cb = set_value_cb

    def publish(self, mqtt, base_list):
        self.mqtt = mqtt

        base_list[-1] = self.property_id
        self.value_topic = "/".join(base_list)
        self.mqtt.publish(self.value_topic, self.init_value, True, 1)
        print (self.value_topic , self.init_value)

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

        if self.set_value_cb:
            base_list[-1] = "$settable"
            publish( self.mqtt, base_list, "true")
            base_list[-1] = "set"
            self.mqtt.subscribe("/".join(base_list), 1)

    def set_value(self, value):
        self.mqtt.publish( self.value_topic, value, True, 1)

    def call_cb(self, topic_split, value):
        if topic_split[3] == self.property_id:
            self.set_value_cb(topic_split, value)
            return True
        else:
            return False

def my_cb(topic_split, value):
    print ("custom cb", topic_split[-1], value)

props_color = [ Property("color", "desired color RGB", "color", None, "rgb", "0,0,0", my_cb) ]
dim_props = [ Property("chan_a", "Dimmer A", "integer", "%", "0:100", 0, my_cb), Property("chan_b", "Dimmer B", "integer", "%", "0:100", 0, my_cb), Property("chan_c", "Dimmer C", "integer", "%", "0:100", 0, my_cb), Property("chan_d", "Dimmer D", "integer", "%", "0:100", 0, my_cb) ]
nodes = [ Node("color", "Color leds (on ABC)", props_color), Node("dimmer", "Dimmers channels", dim_props) ]
device = HomieDevice( ubinascii.hexlify(machine.unique_id()), nodes, "Multicontroler")

while(True):
    device.mqtt.check_msg()
    time.sleep(.050)
