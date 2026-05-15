import requests
import sys 
import json 

url = 'http://127.0.0.1:1081/api/kb/mount'

fn = './mount.json'
data=open(fn, "r").read()
print("data =->", data)
jsdata =  json.loads( data ) 

print("jsdata=->", jsdata)
resp = requests.post(url, json=jsdata )

print('resp->', resp.status_code, resp.text)