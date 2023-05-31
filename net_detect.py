import os
import time
import redis
import subprocess

appl_db = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
config_db = redis.Redis(host='localhost', port=6379, db=4, decode_responses=True)

def get_net_detect_time():
    global config_db
    return (config_db.hget("NET_DETECT_CONFIG|interval", "time"))

def get_gateway_ip():
    gateway_ip_list = []
    command = ["vtysh", "-c", "show bgp peerhash"]
    p = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode == 0:
        for i in str(stdout).split('\n'):
            if i.startswith("\tPeer: "):
                gateway_ip_list.append(i.split(' ')[1])
    return gateway_ip_list

def get_resource_ip():
    global appl_db
    resource_keys = appl_db.keys("COMPUTE_RESOURCE*")
    resource_ip_list = [ ":".join(i.split(":")[1:]) for i in resource_keys ]
    return resource_ip_list

def get_net_status_ip():
    global appl_db
    net_status_keys = appl_db.keys("NET_DETECT_STATUS*")
    net_status_ip_list = [ ":".join(i.split(":")[1:]) for i in net_status_keys ]
    return net_status_ip_list

def set_ip_addr_delay(ip, ntype, delay):
    global appl_db
    table_name = "NET_DETECT_STATUS:{0}".format(ip)
    value = {"type": ntype, "delay": delay }
    appl_db.hmset(table_name, value)

def delete_net_status_ip(ip):
    global appl_db
    table_name = "NET_DETECT_STATUS:{0}".format(ip)
    appl_db.delete(table_name)


def get_neighbour_ip():
    global appl_db
    net_status_keys = appl_db.keys("NEIGHBOUR_DETECT_STATUS*")
    net_status_ip_list = [ ":".join(i.split(":")[1:]) for i in net_status_keys ]
    return net_status_ip_list

def set_neighbour_delay(ip, ntype, delay):
    global appl_db
    table_name = "NEIGHBOUR_DETECT_STATUS:{0}".format(ip)
    value = {"type": ntype, "delay": delay }
    appl_db.hmset(table_name, value)

def delete_neighbour_ip(ip):
    global appl_db
    table_name = "NEIGHBOUR_DETECT_STATUS:{0}".format(ip)
    appl_db.delete(table_name)


def getstatusoutput(cmd):
    try:
        pipe = os.popen(cmd + " 2>&1", 'r')
        text = pipe.read()
        sts = pipe.close()
        if sts is None: sts=0
        if text[-1:] == "\n": text = text[:-1]
        return sts, text
    except:
        return 0, 'error'

def getoutput(cmd):
    result = getstatusoutput(cmd)
    return result[1]

if __name__ == "__main__":
    while True:
        try:
            detect_time = int(get_net_detect_time())
        except:
            #print("get detect time error")
            continue

        times = 3
        old_ip_list = get_net_status_ip()
        old_neighbour_list = get_neighbour_ip()

        gateway_ip_list = get_gateway_ip()
        for ip in gateway_ip_list:
            try:
                time_ms = int(float(getoutput("ping -c{0} {1} | grep avg | cut -d= -f2 | cut -d/ -f2".format(times, ip))))
            except:
                time_ms = "forever"
            set_neighbour_delay(ip, "gateway", time_ms)
            if ip in old_neighbour_list:
                old_neighbour_list.remove(ip)
        for ip in old_neighbour_list:
            delete_neighbour_ip(ip)

        resource_ip_list = get_resource_ip()
        for ip in resource_ip_list:
            try:
                time_ms = int(float(getoutput("ping -c{0} {1} | grep avg | cut -d= -f2 | cut -d/ -f2".format(times, ip))))
            except:
                time_ms = "forever"
            set_ip_addr_delay(ip, "resource", time_ms)
            if ip in old_ip_list:
                old_ip_list.remove(ip)
        for ip in old_ip_list:
            delete_net_status_ip(ip)

        time.sleep(detect_time)
