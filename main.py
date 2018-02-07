import robust
import machine
import ubinascii
import time
import dht
import ujson

config = {
"client_id" : b"esp8266_" + ubinascii.hexlify(machine.unique_id()),
"broker" : "192.168.2.25",
"topic" : "croulebarbe/salon/ledsBuffet",
"dht_pin" : 0
}

class Callback(object):
    def __init__(self, pwm):
        self.pwm = pwm

    def set_dimmer(self, topic, msg):
        self.pwm.duty(int(msg))

def main_loop():

    try:
        with open("config.json", "rt") as cfg_file:
             config.update( ujson.loads( cfg_file.read() ) )
    except OSError:
        pass

    dim_state_str = "%s/dimmer/state"
    sensor_temp_str = config['topic'] + "/sensor/temperature"
    sensor_humid_str = config['topic'] + "/sensor/humidity"

    pwm = machine.PWM(machine.Pin(14))
    pwm.duty(0)
    pwm.freq(500)

    #~ plus_bt = machine.Pin(2)
    plus_bt = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_UP)
    minus_bt = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP)

    last_value = 0

    plus_cnt = 0
    minus_cnt = 0

    delta = 50

    on_off = False

    cb = Callback(pwm)

    client = robust.MQTTClient(config["client_id"], config["broker"])
    client.connect()
    client.set_callback(cb.set_dimmer)
    client.subscribe(config["topic"]+'/dimmer/command', 1)

    if config["dht_pin"] != None:
        d = dht.DHT22(machine.Pin(config["dht_pin"]))
    else:
        d = None

    time_tmp = 0
    try:
        while True:
            client.check_msg()
            time.sleep(.050)
            if d != None and (time.time() % 60) == 0 and time_tmp != int(time.time()):
                time_tmp = int(time.time())
                d.measure()
                client.publish(sensor_temp_str, str(d.temperature()))

                if (time.time() % (60*30)) == 0:
                    client.publish(sensor_humid_str, str(d.humidity()))


            if plus_bt.value() == 0:
                if plus_cnt > 10 and plus_cnt % 4 == 0:
                    plus_cnt += 1
                    val = pwm.duty() + delta
                    if val < 0:
                        val = 0
                    pwm.duty( val )
                    if pwm.duty() == 0 or pwm.duty() == 1023 :
                        delta = -delta
                    print(pwm.duty(), delta)
                    client.publish(dim_state_str % (config['topic'], ), str(pwm.duty()) )
                else:
                    plus_cnt += 1
            elif 0 < plus_cnt <= 10:
                if pwm.duty() == 0:
                    pwm.duty(last_value)
                else:
                    last_value = pwm.duty()
                    pwm.duty(0)
                client.publish(dim_state_str % (config['topic'], ), str(pwm.duty()) )
                plus_cnt = 0
            else:
                plus_cnt = 0

    except Exception as excp:
        print(excp)
    finally:
        client.disconnect()

main_loop()
