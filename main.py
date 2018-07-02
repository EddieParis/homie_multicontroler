import robust
import machine
import ubinascii
import time
import dht
import ujson
import sys

config = {
"client_id" : b"esp8266_" + ubinascii.hexlify(machine.unique_id()),
"broker" : "192.168.2.25",
"topic" : "default_topic",
"dht" : False,
"analog_period" : 0,
"debug" : False
}

class Callback(object):
    def __init__(self, pwm):
        self.pwm = pwm

    def set_dimmer(self, topic, msg):
        # we get bytes, convert to unicode str
        msg=msg.decode("utf-8")
        index = topic.rfind(b"/command")
        # if command can't be found, this is a bad topic
        if index == -1:
            return
        channel = topic[index-1:index]
        if channel == b'g':
            for chan, val in enumerate(msg.split(";")):
                self.pwm[chan].duty(int(val))
        else:
            self.pwm[int(channel)].duty(int(msg))

class ButtonPwm(object):

    dim_state_str = "{}/dimmer/{}/state"

    def __init__(self, mqtt_client, channel, pwm, bt_pin):
        self.mqtt = mqtt_client
        self.channel = channel
        self.pwm = pwm
        self.button = machine.Pin(bt_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.time_cnt = 0
        self.last_value = 0
        self.delta = 25

    def periodic(self):
        """Short press (less than 10 calls) switches on and off, long press (more than 10 calls)
        increases brightness (every 2 calls) and when at maximum decrease brightness to zero while button is pressed.

        Buttons are active low, hardware uses internall ESP pull up for open position.
        """
        if self.button.value() == 0:
            if self.time_cnt > 10 and self.time_cnt % 2 == 0:
                self.time_cnt += 1
                self.pwm.duty( self.pwm.duty() + self.delta )
                if self.pwm.duty() == 0 or self.pwm.duty() == 1023 :
                    self.delta = -self.delta
                print(self.pwm.duty(), self.delta)
                self.mqtt.publish(ButtonPwm.dim_state_str.format(config['topic'], self.channel), str(self.pwm.duty()) )
            else:
                self.time_cnt += 1
        elif 0 < self.time_cnt <= 10:
            if self.pwm.duty() == 0:
                self.pwm.duty(self.last_value)
            else:
                self.last_value = self.pwm.duty()
                self.pwm.duty(0)
            self.mqtt.publish(ButtonPwm.dim_state_str.format(config['topic'], self.channel), str(self.pwm.duty()) )
            self.time_cnt = 0
        else:
            self.time_cnt = 0

def main_loop():

    try:
        with open("config.json", "rt") as cfg_file:
             config.update( ujson.loads( cfg_file.read() ) )
    except OSError:
        pass


    sensor_temp_str = config['topic'] + "/sensor/temperature"
    sensor_humid_str = config['topic'] + "/sensor/humidity"

    #create the pwm channels
    pwm0 = machine.PWM(machine.Pin(12), duty=0, freq=150)
    pwm1 = machine.PWM(machine.Pin(13), duty=0)
    pwm2 = machine.PWM(machine.Pin(15), duty=0)

    pwm = [pwm0, pwm1, pwm2]

    cb = Callback(pwm)


    robust.MQTTClient.DEBUG = True

    #create the mqtt client using config parameters
    client = robust.MQTTClient(config["client_id"], config["broker"])
    client.connect()
    client.set_callback(cb.set_dimmer)
    client.subscribe(config["topic"]+'/dimmer/+/command', 1)

    #create dht if it is enabled in config
    if config["dht"] == True:
        d = dht.DHT22(machine.Pin(0))
    else:
        d = None

    #check in config for analog period
    analog_period = config['analog_period']
    if analog_period != 0:
        adc = machine.ADC(0)
    else:
        adc = None

    #create the buttons and pwm channels
    bt_pwm_1 = ButtonPwm(client, 0, pwm0, 4)
    bt_pwm_2 = ButtonPwm(client, 1, pwm1, 5)
    bt_pwm_3 = ButtonPwm(client, 2, pwm2, 14)

    time_tmp = 0

    dht_retry = 0

    dht_err_ctr = 0

    try:
        while True:
            client.check_msg()
            time.sleep(.050)

            cur_time = int(time.time())

            #this simple test enables to get in this loop every second
            if time_tmp != cur_time:
                #~ print("In the loop")
                time_tmp = cur_time

                #tempeature is read from dht periodically
                if d != None and (cur_time % 60) == dht_retry :
                    try:
                        d.measure()
                    except (OSError, dht.DHTChecsumError) as excp:
                        #If we have an exception, retry in 4 seconds
                        dht_retry +=4
                        dht_err_ctr += 1
                        if dht_retry == 40:
                            #too many retries, raise the original exception
                            raise
                        else:
                            #logging
                            client.publish("{}/stat/dhterror".format(config['topic']), str(dht_err_ctr))
                            print("DHT error, retrying")
                    else:
                        dht_retry = 0
                        dht_err_ctr = 0
                        #all went well let's publish temperature
                        client.publish(sensor_temp_str, str(d.temperature()))
                        print(d.temperature())

                        #publish humidity
                        if (cur_time % (60*30)) == dht_retry:
                            client.publish(sensor_humid_str, str(d.humidity()))

                #analog publication period is user defined
                if analog_period and (cur_time % analog_period):
                    adc.read()
                    client.publish("{}/sensor/analog".format(config['topic']), str(adc.read()/1023.0) )

            #buttons checks
            bt_pwm_1.periodic()
            bt_pwm_2.periodic()
            bt_pwm_3.periodic()

    except KeyboardInterrupt as excp:
        print ("Interrupted")
        sys.print_exception(excp)

    except Exception as excp:
        sys.print_exception(excp)

        #if debug mode is not enabled in config automatic reset in 10 seconds
        if config['debug'] == False:
            for count in range (10,0, -1):
                print("Reboot in {} seconds\r".format(count))
                time.sleep(1)
            machine.reset()
    finally:
        client.disconnect()

main_loop()
