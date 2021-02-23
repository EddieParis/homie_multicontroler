from homie import *

if __name__ == "__main__":
    import robust
    from machine import unique_id
    import ubinascii

    def my_cb(topic_split, value):
        print ("custom cb", topic_split[-1], value)

    MQTT_ID = b"esp32_"+ ubinascii.hexlify(unique_id())

    mqtt = robust.MQTTClient(MQTT_ID, "192.168.2.42")
    mqtt.connect()

    props_color = [ Property("color", "desired color RGB", "color", None, "rgb", "0,0,0", my_cb) ]
    dim_props = [ Property("chan-a", "Dimmer A", "float", None, "0:100", 0, my_cb), Property("chan-b", "Dimmer B", "integer", "%", "0:100", 0, my_cb), Property("chan-c", "Dimmer C", "integer", "%", "0:100", 0, my_cb), Property("chan-d", "Dimmer D", "integer", "%", "0:100", 0, my_cb) ]
    env_props = [ Property("temperature", "Temperature", "float", "°C".encode("utf-8"), None, 0), Property("humidity", "Humidity", "float", "%", "0:100", 0), Property("pressure", "Atmospheric pressure", "float", "mBar", None, 0) ]
    nodes = [ Node("color", "Color leds (on ABC)", props_color), Node("dimmer", "Dimmers channels", dim_props), Node("evironment", "Environment Measures", env_props) ]
    device = HomieDevice(mqtt, ubinascii.hexlify(unique_id()), nodes, "Multicontroler")

    while(True):
        device.mqtt.check_msg()
        time.sleep(.050)
