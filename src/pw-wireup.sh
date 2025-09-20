#!/bin/sh
pactl load-module module-null-sink sink_name=monitor.volt sink_properties=device.description=MonitorVolt
sleep 2
pw-link "alsa_output.usb-Universal_Audio_Volt_276_21512039017647-00.analog-stereo:monitor_FL" "monitor.volt:playback_FL"
pw-link "alsa_output.usb-Universal_Audio_Volt_276_21512039017647-00.analog-stereo:monitor_FR" "monitor.volt:playback_FR"
pw-link "alsa_input.usb-Universal_Audio_Volt_276_21512039017647-00.analog-stereo:capture_FL" "monitor.volt:playback_FL"
pw-link "alsa_input.usb-Universal_Audio_Volt_276_21512039017647-00.analog-stereo:capture_FR" "monitor.volt:playback_FR"
