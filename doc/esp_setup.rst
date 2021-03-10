
tools:

flasher: esptool

file exchange and remote console: webrepl


In the folowing instructions, when you see text surrounded by <> it means you have to replace
with your own values.


../../../tools/esptool/esptool.py  --port /dev/ttyUSB0 erase_flash
esptool.py v3.0-dev
Serial port /dev/ttyUSB0
Connecting.......
Detecting chip type... ESP8266
Chip is ESP8266EX
Features: WiFi
Crystal is 26MHz
MAC: b4:e6:2d:17:f0:1d
Uploading stub...
Running stub...
Stub running...
Erasing flash (this may take a while)...
Chip erase completed successfully in 9.2s
Hard resetting via RTS pin...

[oortigues@localhost esp8266]$ ../../../tools/esptool/esptool.py  --port /dev/ttyUSB0 write_flash 0 ./build-GENERIC/firmware-combined.bin
esptool.py v3.0-dev
Serial port /dev/ttyUSB0
Connecting.....
Detecting chip type... ESP8266
Chip is ESP8266EX
Features: WiFi
Crystal is 26MHz
MAC: b4:e6:2d:17:f0:1d
Uploading stub...
Running stub...
Stub running...
Configuring flash size...
Auto-detected Flash size: 4MB
Flash params set to 0x0040
Compressed 635208 bytes to 417714...
Wrote 635208 bytes (417714 compressed) at 0x00000000 in 38.1 seconds (effective 133.5 kbit/s)...
Hash of data verified.

Leaving...
Hard resetting via RTS pin...
[oortigues@localhost esp8266]$


>>> import wifi_connect
Connects to an access point in dhcp mode
- enter ssid:
<your wifi ssid>
- enter password:
<you wifi password>
connecting to network...
#6 ets_task(4020f560, 28, 3fff9ee0, 10)
network config: ('192.168.2.103', '255.255.255.0', '192.168.2.1', '192.168.2.1')
>>> import webrepl_setup
WebREPL daemon auto-start status: disabled

Would you like to (E)nable or (D)isable it running on boot?
(Empty line to quit)
> E
To enable WebREPL, you must set password for it
New password (4-9 chars): <your webrepl password>
Confirm password: <your webrepl password>
Changes will be activated after reboot
Would you like to reboot now? (y/n) y

tools/webrepl/webrepl_cli.py -p <your webrepl password> boot.py <your-ip>:
do not forget the column sign ':' at the end of the line.

do the same for

* main.py
* homie.py
* env_sensors.py
* robust.py
* simple.py

if you use a bme/p 280 sensor you also need to download bme280.py

For the config I recommend to create a separate json file for each thing and name them explicitely.
However, file on the target must be named config.json. Webrepl can rename while copying hence the command:

>>>> tools/webrepl/webrepl_cli.py -p <your webrepl password> <full_name_of_config>.json <your-ip>:config.json
