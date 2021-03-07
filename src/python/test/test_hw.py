"""
Activate a PWM 50% on a pin and indicate immediate neighbors.
Checks to be done:
    Pin shall show 1.6 V (50% of 3.3V)
    Neighbors shall be near zero or near 3.3 V, but never 1.6

    If you see 0v on the tested pin, it means solder is bad, there is no contact.

    If you find 1.6V on a neighbor, it means there is a short circuit on
    tested pin and the neighbor, cut power and check your soldering immediately,
    do not proceed to other pins.

    If pin is OK, press enter to do next pin.

Finally, software shows ADC values continuously. On ESP 32, one channel
can have some influence to the other, it is not a big deal unless you read very
close values on both channels.

ADC input of esp32 are configured in this software to accept 3.3V so just
short one input to VCC or ground to see if it works.

WARNING for esp8266, 1 Volt max on ADC input.

"""

from machine import Pin, PWM, ADC
import sys
import time

if sys.platform == "esp8266":
    pins = {"dht":0, "sw b":4, "sw c":5, "chan_a":12, "chan_b":13, "sw a":14, "chan_c":15, "scl":16}
    sides = [ None, 15, None, 0, 4, 5, None, 16, 14, 12, 13, None ]
    adcs = [ ADC(0) ]
elif sys.platform == "esp32":
    pins = {"dht":0 , "chan_c":2, "chan_d":4, "ext 5":5, "chan_a":12, "chan_b":13,
            "int 1":14, "ext 16":16, "ext 17":17, "ext 18":18, "ext 19":19,
            "sda":21, "scl":22, "sw c":25, "sw d":26, "int 0":27, "sw a":32, "sw b":33, "adc 0": 34, "adc 1":35}

    sides = [ None, 34, 35, 32, 33, 25, 26, 27, 14, 12, None, 13, None, 2, None, 22, None, 21, None, 19, 18, 5, 17, 16, 4, 0, None ]
    adcs = [ADC(Pin(34)), ADC(Pin(35)) ]
    for adc in adcs:
        adc.atten(ADC.ATTN_11DB)

names = { v:k for k,v in pins.items() }
names.update({None:"none"})

for name in sorted(pins):
    pin_no = pins[name]
    if pin_no in [34, 35]:
        continue
    idx = sides.index(pin_no)
    print("Activating {}, neighbors : {} , {}".format(name, names[sides[idx-1]], names[sides[idx+1]]))

    p=PWM(Pin(pin_no))
    p.freq(150)
    p.duty(512)
    input("next")
    p.deinit()
    p=Pin(pin_no, Pin.IN)

while True:
    for adc in adcs:
        print(adc.read())
    time.sleep(.5)
