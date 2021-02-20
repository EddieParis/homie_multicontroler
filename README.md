# The homie led multicontroler #

This is the [homie](https://homieiot.github.io) compatible led muticontroler project. This project is composed of a software and 2 hardware boards based on esp32 and cheaper esp8266 (to be published soon).

The goal of this project is to provide a multi channel led controller and sensors facility for home automation.

You don't have to be a python or an electronic expert to use this project.

# Main features #
- homie 3.0 and 4.0 compatible (seamless integration with openHAB for instance)
- json configurable
- controls independant leds channels or RGB group (12v and 24v compatible)
- switches for local led control
- build in compatiblility with DHT, DS1820 and BME/P 280 sensors
- build in compatibility with any ADC sensor
- easy to add your own sensors or actuators
- designed to run on micropython
- very robust, ran for several years now

# Configuration #
You will have to provide a configuered json file to the controler, it will be use to determine which platform and which sensor you are using, and then expose the values on the homie side accordingly.
