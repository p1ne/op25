#!/usr/bin/env python3

import sys
import requests
import json
import pifacecad
import time
from threading import Barrier, Thread
from queue import Queue, Empty
import alsaaudio
import subprocess

ON_POSIX = 'posix' in sys.builtin_module_names

q_corr_time = time.time()
cad = pifacecad.PiFaceCAD() 

msg = ""
msg_prev = ""

m = alsaaudio.Mixer('PCM')

current_q = 76

def cad_lcd_ljust(str):
  cad.lcd.write(str.ljust(16))

def vol_up(event = None):
  vol = m.getvolume()
  vol = int(vol[0])
  if vol<90:
    m.setvolume(vol+10)
  else:
    m.setvolume(100)
  cad_lcd_ljust("Vol + (" + str(vol) + ")")
  time.sleep(0.25)

def vol_down(event = None):
  vol = m.getvolume()
  vol = int(vol[0])
  if vol>10:
    m.setvolume(vol-10)
  else:
    m.setvolume(0)
  cad_lcd_ljust("Vol - (" + str(vol) + ")")
  time.sleep(0.25)

def q_up(event = None):
  global current_q 
  r = requests.post('http://localhost:8080', json=[{"command":"freq_corr","data":1}])
  current_q = current_q + 1
  cad_lcd_ljust("Q + (" + str(current_q) + ")")
  print("Q + (" + str(current_q) + ")")
  time.sleep(0.25)

def q_down(event = None):
  global current_q 
  r = requests.post('http://localhost:8080', json=[{"command":"freq_corr","data":-1}])
  current_q = current_q - 1
  cad_lcd_ljust("Q - (" + str(current_q) + ")")
  print("Q - (" + str(current_q) + ")")
  time.sleep(0.25)

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

global end_barrier
end_barrier = Barrier(2)

switchlistener = pifacecad.SwitchEventListener(chip=cad)
switchlistener.register(0, pifacecad.IODIR_ON, q_down)
switchlistener.register(1, pifacecad.IODIR_ON, q_up)
switchlistener.register(6, pifacecad.IODIR_ON, vol_down)
switchlistener.register(7, pifacecad.IODIR_ON, vol_up)
switchlistener.activate()

rxp = subprocess.Popen(["/usr/bin/python", "./rx.py", "--args", "rtl=0", "--gains", "lna:35", "-S", "960000", "-T", "trunk.tsv", "-l", "http:0.0.0.0:8080", "-u", "23456", "-w", "-W", "192.168.88.226", "-q", str(current_q), "-V", "-v", "1"], cwd="./apps",stderr=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=ON_POSIX, bufsize=1)
rxq = Queue()
rxt = Thread(target=enqueue_output, args=(rxp.stderr, rxq))
rxt.daemon = True 
rxt.start()

time.sleep(10)

cad.lcd.backlight_on()
cad.lcd.cursor_off()
cad.lcd.blink_off()
cad_lcd_ljust("Loading...")

while True:
  r = requests.post('http://localhost:8080', json=[{"command":"update","data":0}])
  j=r.json()
  cad.lcd.set_cursor(0,1)
  cad_lcd_ljust("Q: " + str(current_q))

  if len(j) > 0 and 'tgid' in j[0] and j[0]['tgid'] != None:
    msg = str(j[0]['tag']).replace("Talkgroup ","")
    if msg != msg_prev:
      cad.lcd.set_cursor(0,0)
      cad_lcd_ljust(msg)
      msg_prev = msg
  time.sleep(1)
  while True:
    try:
      line = rxq.get_nowait()
    except Empty:
      break 
    else:
      #print(line)
      if (line == b'p25_framer::rx_sym() tuning error -1200\n') and (time.time() - q_corr_time > 5):
        q_corr_time = time.time()
        q_up()
      if (line == b'p25_framer::rx_sym() tuning error +1200\n') and (time.time() - q_corr_time > 5):
        q_corr_time = time.time()
        q_down()

end_barrier.wait()  # wait unitl exit
switchlistener.deactivate()
rxt.stop()
