import time
from micropython import const

VERSION = "3.0"

KEEP_ALIVE = const(60)
log = True


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
        self.state_topic = "/".join(base_list)
        self.mqtt.set_last_will(self.state_topic, "lost", True, 1)

        self.mqtt.connect(clean_session=True)
        self.mqtt.disconnect()
        self.mqtt.connect(clean_session=False)

        base_list[-1] = "$homie"
        self.publish(base_list, VERSION)

        base_list[-1] = "$name"
        self.name_topic = self.publish(base_list, nice_device_name)

        self.publish(self.state_topic, "init")

        base_list[-1] = "$nodes"
        self.publish(base_list, ",".join([node.node_id for node in self.nodes]))

        settable = False
        for node in nodes:
            settable |= node.expose(self, list(base_list))
        if settable:
            base_list[-1] = "+"
            base_list.append("+")
            base_list.append("set")
            mqtt.subscribe("/".join(base_list), 1)

        time.sleep(1)
        while(mqtt.check_msg()):
            pass

        if broadcast_cb:
            mqtt.subscribe("/".join([self.base, self.BROADCAST, '#']), 1)

        self.ready()

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

    def publish(self, topic, value, qos=1, retained=True):
        if isinstance(topic, list):
            joint_topic = "/".join(topic)
        else:
            joint_topic = topic
        if log:
            print(joint_topic, value)
        self.mqtt.publish(joint_topic, value, retained, qos)
        return joint_topic

    def alert(self):
        self.state = "alert"
        self.publish_state()

    def ready(self):
        self.state = "ready"
        self.publish_state()

    def publish_state(self):
        self.publish(self.state_topic, self.state, 1)
        self.last_state_epoc = time.time()

    def main(self):
        self.mqtt.check_msg()
        now = time.time()
        if now - self.last_state_epoc > KEEP_ALIVE:
            self.publish_state()


class Node:
    def __init__(self, node_id, name, properties):
        self.node_id = node_id
        self.name = name
        self.properties = properties

    def expose(self, homie, base_list):
        base_list[-1] = self.node_id

        base_list.append("$name")
        homie.publish(base_list, self.name)

        base_list[-1] = "$properties"
        homie.publish(base_list, ",".join([prop.property_id for prop in self.properties]))

        settable = False
        for prop in self.properties:
            settable |= prop.expose(homie, list(base_list))
        return settable

    def action_set(self, topic_split, value):
        if topic_split[2] == self.node_id:
            for prop in self.properties:
                if prop.check_msg(topic_split, value):
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

    def expose(self, homie, base_list):
        self.homie = homie

        base_list[-1] = self.property_id
        self.value_topic = self.homie.publish(base_list, self.init_value)

        base_list.append("$name")
        self.homie.publish(base_list, self.name)

        base_list[-1] = "$datatype"
        self.homie.publish(base_list, self.type)

        if self.unit:
            base_list[-1] = "$unit"
            self.homie.publish(base_list, self.unit)

        if self.format:
            base_list[-1] = "$format"
            self.homie.publish(base_list, self.format)

        if not self.retained:
            base_list[-1] = "$retained"
            self.homie.publish(base_list, "false")

        if self.value_set_cb:
            base_list[-1] = "$settable"
            self.homie.publish(base_list, "true")
            return True
        return False

    def alert(self):
        self.homie.alert()

    def send_value(self, value):
        self.homie.publish(self.value_topic, value, 1, self.retained)

    def check_msg(self, topic_split, value):
        if topic_split[3] == self.property_id and self.value_set_cb:
            if self.value_set_cb(topic_split, value):
                self.send_value(value)
            return True
        else:
            return False
