import robust
from machine import Pin, PWM, ADC, I2C, RTC, reset
import ubinascii
import time
import ujson
import sys
import network
import math

import ntptime

import homie
import env_sensors

config = {
"esp32" : False,
"client_id" : b"esp_" + ubinascii.hexlify(network.WLAN().config('mac')),
"broker" : "192.168.2.25",
"location" : "",
"dht" : False,
"ds1820" : False,
"bme280" : False,
"analog_period" : 0,
"analog_bits" : 10,
"analog_attn": 0,
"analog2_period" : 0,
"analog2_bits" : 10,
"analog2_attn": 0,
"debug" : False
}

class ColorManager:
    def __init__(self, dimmers):
        self.props = [ homie.Property("color", "desired color RGB", "color", None, "rgb", "000,000,000", self.set_color),
                        homie.Property("cycler", "cycler mode", "integer", None, None, "0", self.set_cycler) ]
        self.dimmers = dimmers[:3]
        self.cycle = 0
        self.angles = [math.pi,math.pi,math.pi]
        self.increments = [math.pi/180, math.pi/260, math.pi/225]
        for dimmer in self.dimmers:
            dimmer.cycler = self

    def set_color(self, topic, value):
        for dimmer, val in zip(self.dimmers, value.split(",")):
            dimmer.pwm.duty(int(float(val)*1023/255))
        return True

    def do_cycle(self):
        if self.cycle:
            for angle, dimmer in zip(self.angles, self.dimmers):
                dimmer.pwm.duty(int(511*math.cos(angle)+511))
            self.angles = [ (angle + inc*self.cycle)%(math.pi*2) for angle, inc in zip(self.angles, self.increments) ]

    def stop_cycling(self):
        if self.cycle:
            self.cycle = 0
            self.props[1].send_value(str(0))

    def set_cycler(self, topic, value):
        self.cycle = int(value)
        return True


class Dimmer(homie.Property):

    def __init__(self, dim_id, pwm, bt_pin):
        super(Dimmer, self).__init__("chan_"+dim_id.lower(), "Dimmer "+dim_id.upper(), "float", "%", "0:100", 0, self.set_value)
        self.pwm = pwm
        self.button = Pin(bt_pin, Pin.IN, Pin.PULL_UP)
        self.time_cnt = 0
        self.last_value = 0
        self.delta = 25
        self.top_pause = 0
        self.cycler = None

    def periodic(self):
        """Short press (less than 10 calls) switches on and off, long press (more than 10 calls)
        increases brightness (every 2 calls) and when at maximum decrease brightness to zero while button is pressed.

        Buttons are active low, hardware uses internall ESP pull up for open position.
        """
        if self.button.value() == 0:
            if self.time_cnt > 10 and self.time_cnt % 2 == 0 and self.top_pause == 0:
                self.time_cnt += 1
                self.pwm.duty( self.pwm.duty() + self.delta )
                if self.pwm.duty() == 0:
                    self.delta = -self.delta
                elif self.pwm.duty() == 1023:
                    self.delta = -self.delta
                    self.top_pause = 15
                print(self.pwm.duty(), self.delta)
                self.send_value(str(int(self.pwm.duty()/1023*100)))
            else:
                self.time_cnt += 1
                if self.cycler and self.cycler.cycle:
                    self.time_cnt = -1
                if self.top_pause:
                    self.top_pause -= 1
        elif 0 < self.time_cnt <= 10:
            self.top_pause = 0
            if self.pwm.duty() == 0:
                self.pwm.duty(self.last_value)
            else:
                self.last_value = self.pwm.duty()
                self.pwm.duty(0)
            self.send_value(str(int(self.pwm.duty()/1023*100)))
            self.time_cnt = 0
        elif self.time_cnt == -1:
            self.cycler.stop_cycling()
            self.time_cnt = 0
        else:
            self.time_cnt = 0

    def set_value(self, topic, value):
        self.pwm.duty(int(float(value)/100*1023))
        return True

class Analog(homie.Property):
    maxes=[1,1.34,2,3.6]
    def __init__(self, prop_id, prop_name, pin, period, bits=10, attn=0):
        super(Analog, self).__init__(prop_id, prop_name, "float", None, "0:{}".format(Analog.maxes[attn]), 0)
        if config["esp32"]:
            pin = Pin(pin)
        self.adc = ADC(pin)
        if config["esp32"]:
            self.adc.atten(attn)
            self.adc.width(bits-9)
        self.period = period
        self.range = (2**bits)-1
        self.max = Analog.maxes[attn]

    def periodic(self, cur_time):
        if (cur_time % self.period) == 0:
            print(self.adc.read())
            self.send_value(str(self.max*self.adc.read()/self.range))

def homie_broadcast_cb(topic, value, retained):
    print("broadcast :", topic, value, retained)

def main_loop():

    init_done = False

    ntptime.host = "fr.pool.ntp.org"
    ntptime.settime()

    try:
        with open("config.json", "rt") as cfg_file:
             config.update( ujson.loads( cfg_file.read() ) )
    except OSError:
        pass

    try:
        #create the pwm channels
        pwm0 = PWM(Pin(12), duty=0)
        pwm0.freq(150)
        pwm1 = PWM(Pin(13), duty=0)
        if config["esp32"]:
            pwm2 = PWM(Pin(2), duty=0)
            pwm3 = PWM(Pin(4), duty=0)
        else:
            pwm2 = PWM(Pin(15), duty=0)

        #create dht if it is enabled in config
        if config["dht"]:
            env_nodes = [env_sensors.EnvironmentDht()]
        elif config["ds1820"]:
            import onewire, ds18x20
            ds_driver = ds18x20.DS18X20(onewire.OneWire(Pin(0)))
            env_nodes = [env_sensors.EnvironmentDS1820(ds_driver, rom, num) for num, rom in enumerate(ds_driver.scan())]
        elif config["bme280"]:
            if config["esp32"]:
                i2c = I2C(0, scl=Pin(22), sda=Pin(21))
            else:
                i2c = I2C(scl=Pin(16), sda=Pin(0))
            devices = i2c.scan()
            bme_addrs = [addr for addr in devices if addr == 0x76 or addr == 0x77]
            env_nodes = [env_sensors.EnvironmentBME280(i2c, addr, num) for num, addr in enumerate(bme_addrs)]
        else:
            env_nodes = []

        adcs = []
        #check in config for analog period
        analog_period = config['analog_period']
        analog2_period = config['analog2_period']
        if config["esp32"]:
            if analog_period != 0:
                adcs.append(Analog("analog1", "Analog sensor 1", 34, analog_period, config["analog_bits"], config["analog_attn"]))
            if analog2_period != 0:
                adcs.append(Analog("analog2", "Analog sensor 2", 35, analog2_period, config["analog2_bits"], config["analog2_attn"]))
        else:
            if analog_period != 0:
                adcs.append(Analog("analog1", "Analog sensor 1", 0, analog_period))

        #create the buttons and pwm channels

        if config["esp32"]:
            dimmers = [ Dimmer("A", pwm0, 32), Dimmer("B", pwm1, 33),
                        Dimmer("C", pwm2, 25), Dimmer("D", pwm3, 26) ]
        else:
            dimmers = [ Dimmer("A", pwm0, 4), Dimmer("B", pwm1, 5), Dimmer("C", pwm2, 14) ]

        color_manager = ColorManager(dimmers)

        nodes = [ homie.Node("color", "Color leds (on ABC)", color_manager.props), homie.Node("dimmer", "Dimmers channels", dimmers)]

        if env_nodes:
            nodes.extend(env_nodes)

        if adcs:
            nodes.append(homie.Node("analog_sens", "Analog Sensors", adcs))

        init_done = True

        #~ robust.MQTTClient.DEBUG = True

        #create the mqtt client using config parameters
        mqtt = robust.MQTTClient(config["client_id"], config["broker"], keepalive=4*homie.KEEP_ALIVE)

        device = homie.HomieDevice( mqtt, ubinascii.hexlify(network.WLAN().config('mac')), nodes, "Multicontroler{}".format(config["location"]), homie_broadcast_cb)

        time_tmp = 0

        while True:
            device.main()
            time.sleep(.050)

            cur_time = int(time.time())

            color_manager.do_cycle()

            #this simple test enables to get in this loop only once per second
            if time_tmp != cur_time:
                #~ print("In the loop")
                time_tmp = cur_time

                for env_node in env_nodes:
                    env_node.periodic(cur_time)

                #analog publication period is user defined
                for adc in adcs:
                    adc.periodic(cur_time)

            #buttons checks
            for dimmer in dimmers:
                dimmer.periodic()

    except KeyboardInterrupt as excp:
        print ("Interrupted")
        sys.print_exception(excp)

    except Exception as excp:
        sys.print_exception(excp)
        with open("exceptions.txt", "at") as excp_file:
            excp_file.write(str(RTC().datetime()))
            excp_file.write(" GMT\n")
            sys.print_exception(excp, excp_file)
            excp_file.write("\n")

        #if debug mode is not enabled in config automatic reset in 10 seconds
        if config['debug'] == False and init_done == True:
            mqtt.disconnect()
            for count in range (10,0, -1):
                print("Reboot in {} seconds\r".format(count))
                time.sleep(1)
            reset()
    finally:
        mqtt.disconnect()

main_loop()
