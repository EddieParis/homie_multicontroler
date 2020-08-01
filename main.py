import robust
import machine
import ubinascii
import time
import ujson
import sys
import network
import math

import ntptime

import dht
import bme280
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
"analog_period2" : 0,
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
        self.button = machine.Pin(bt_pin, machine.Pin.IN, machine.Pin.PULL_UP)
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
                self.send_value(str(self.pwm.duty()/1023))
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
            self.send_value(str(self.pwm.duty()/1023))
            self.time_cnt = 0
        elif self.time_cnt == -1:
            self.cycler.stop_cycling()
            self.time_cnt = 0
        else:
            self.time_cnt = 0

    def set_value(self, topic, value):
        self.pwm.duty(int(float(value)*1023))
        return True

class Analog(homie.Property):
    def __init__(self, prop_id, prop_name, pin, period):
        super(Analog, self).__init__(prop_id, prop_name, "float", None, "0:1", 0)
        if config["esp32"]:
            pin = machine.Pin(pin)
        self.adc = machine.ADC(pin)
        self.period = period

    def periodic(self, cur_time):
        if (cur_time % self.period) == 0:
            self.send_value(str(self.adc.read()/1023.0))

def homie_broadcast_cb(topic, value, retained):
    print("broadcast :", topic, value, retained)

def main_loop():

    try:
        with open("config.json", "rt") as cfg_file:
             config.update( ujson.loads( cfg_file.read() ) )
    except OSError:
        pass

    #create the pwm channels
    pwm0 = machine.PWM(machine.Pin(12), duty=0, freq=150)
    pwm1 = machine.PWM(machine.Pin(13), duty=0)
    if config["esp32"]:
        pwm2 = machine.PWM(machine.Pin(2), duty=0)
        pwm3 = machine.PWM(machine.Pin(4), duty=0)
    else:
        pwm2 = machine.PWM(machine.Pin(15), duty=0)


    #~ robust.MQTTClient.DEBUG = True

    #create the mqtt client using config parameters
    client = robust.MQTTClient(config["client_id"], config["broker"], keepalive=homie.NAME_SEND_INTERVAL)


    #create dht if it is enabled in config
    if config["dht"]:
        env_nodes = [env_sensors.EnvironmentDht()]
    elif config["ds1820"]:
        import onewire, ds18x20
        ds_driver = ds18x20.DS18X20(onewire.OneWire(machine.Pin(0)))
        env_nodes = [env_sensors.EnvironmentDS1820(ds_driver, rom, num) for num, rom in enumerate(ds_driver.scan())]
    elif config["bme280"]:
        if config["esp32"]:
            i2c = machine.I2C(0, scl=machine.Pin(22), sda=machine.Pin(21))
        else:
            i2c = machine.I2C(scl=machine.Pin(16), sda=machine.Pin(0))
        devices = i2c.scan()
        bme_addrs = [addr for addr in devices if addr == 0x76 or addr == 0x77]
        env_nodes = [env_sensors.EnvironmentBME280(i2c, addr, num) for num, addr in enumerate(bme_addrs)]
    else:
        env_nodes = None

    adcs = []
    #check in config for analog period
    analog_period = config['analog_period']
    analog_period2 = config['analog_period2']
    if config["esp32"]:
        if analog_period != 0:
            adcs.append(Analog("analog1", "Analog sensor 1", 34, analog_period))
        if analog_period2 != 0:
            adcs.append(Analog("analog2", "Analog sensor 2", 35, analog_period2))
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

    device = homie.HomieDevice( client, ubinascii.hexlify(network.WLAN().config('mac')), nodes, "Multicontroler{}".format(config["location"]), homie_broadcast_cb)

    time_tmp = 0

    dht_retry = 0

    dht_err_ctr = 0

    try:
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
            excp_file.write(str(machine.RTC().datetime()))
            excp_file.write(" GMT\n")
            sys.print_exception(excp, excp_file)
            excp_file.write("\n")

        #if debug mode is not enabled in config automatic reset in 10 seconds
        if config['debug'] == False:
            for count in range (10,0, -1):
                print("Reboot in {} seconds\r".format(count))
                time.sleep(1)
            machine.reset()
    finally:
        client.disconnect()

ntptime.settime()

main_loop()
