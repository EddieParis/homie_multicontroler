import homie

class EnironmentNode(homie.Node):
    def __init__(self, props, num):
        ext = ""
        if num:
            ext = str(num)
        super().__init__("environment"+ext, "Environment Measures", props)

    def get_temp_prop(self):
        return homie.Property("temperature", "Temperature", "float", "°C".encode("utf-8"), None, 0)

    def get_humid_prop(self):
        return homie.Property("humidity", "Humidity", "float", "%", "0:100", 0)

    def get_press_prop(self):
        return homie.Property("pressure", "Atmospheric pressure", "float", "mBar", None, 0)

class EnvironmentDht(EnironmentNode):
    def __init__(self):
        super().__init__([self.get_temp_prop(), self.get_humid_prop()], None)
        import dht
        import machine
        self.dht_retry = 0
        self.dht_err_ctr = 0
        self.driver = temp_sensor = dht.DHT22(machine.Pin(0))

    def periodic(self, now):
        if (now % 60) == self.dht_retry :
            try:
                self.driver.measure()
            except (OSError, dht.DHTChecsumError) as excp:
                #If we have an exception, retry in 4 seconds
                self.dht_retry +=4
                self.dht_err_ctr += 1
                if self.dht_retry == 40:
                    #too many retries, raise the original exception
                    raise
                else:
                    #logging
                    print("DHT error, retrying")
            else:
                self.dht_retry = 0
                self.dht_err_ctr = 0
                #all went well let's publish temperature
                self.properties[0].send_value(str(self.driver.temperature()))
                print(self.driver.temperature())

                #publish humidity
                if (now % (60*30)) == self.dht_retry:
                    self.properties[1].send_value(str(self.driver.humidity()))

class EnvironmentDS1820(EnironmentNode):
    def __init__(self, driver, rom_id, num):
        super().__init__([self.get_temp_prop()], num)
        self.num = num
        self.driver = driver
        self.rom_id = rom_id

    def periodic(self, now):
        if (now % 60) == 0 and not self.num:
            self.driver.convert_temp()
        elif (now % 60) == 1:
            temp = self.driver.read_temp(self.rom_id)
            #all went well let's publish temperature
            self.properties[0].send_value('{:.1f}'.format(temp))
            print(temp)

class EnvironmentBME280(EnironmentNode):
    def __init__(self, i2c, addr, num):
        import bme280
        self.driver = bme280.BME280(address=addr, i2c=i2c)
        if self.driver.humidity_capable:
            super().__init__([self.get_temp_prop(), self.get_press_prop(), self.get_humid_prop()], num)
        else:
            super().__init__([self.get_temp_prop(), self.get_press_prop()], num)

    def periodic(self, now):
        if (now % 60) == 0:
            temp,pa,hum = self.driver.read_compensated_data()
            self.properties[0].send_value('{:.1f}'.format(temp/100))
            self.properties[1].send_value('{:.2f}'.format(pa/25600))
            if self.driver.humidity_capable:
                self.properties[2].send_value(str(hum//1024))
            print (temp/100,pa//25600,hum/1024)
