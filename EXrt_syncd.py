import os
import time
import redis
import subprocess

appl_db = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def read_enhancedgw_from_file():
    if not os.path.exists("/tmp/enhancedgw"):
        return []
    content = open("/tmp/enhancedgw","r").read().strip()

    try:
        if content[-3:] != "end":
            return []
    except:
        return []

    l = content.split('\n')
    l = [i.strip() for i in l][:-1]
    return l

def set_compute_route(gw_ip, ip, cpu_num, ephemeral_storage, hugepages_1gi, hugepages_2mi, mem_size, pods, delay, nh):
    global appl_db
    table_name = "COMPUTE_ROUTE:{0}:{1}".format(gw_ip, ip)
    value = {"cpu": cpu_num, "ephemeral_storage": ephemeral_storage, "gpu": hugepages_1gi, "hugepages_2mi": hugepages_2mi, "memory": mem_size, "pods": pods, "delay": delay, "nexthop": nh}
    appl_db.hmset(table_name, value)

def get_compute_route():
    global appl_db
    keys = appl_db.keys("COMPUTE_ROUTE*")
    keys = [ key.encode('utf-8') for key in keys]
    return keys

def delete_compute_route(table_name):
    global appl_db
    appl_db.delete(table_name)

def find_in_A_not_in_B(A,B):
    # deepcopy
    AA = [i for i in A]
    for i in B:
        if i in AA:
            AA.remove(i)
    return AA

def run_command(command, shell=False, hide_errors=False):
    """
    Run a linux command. The command is defined as a list. See subprocess.Popen documentation on format
    :param command: command to execute. Type: List of strings
    :param shell: execute the command through shell when True. Type: Boolean
    :param hide_errors: don't report errors to syslog when True. Type: Boolean
    :return: Tuple: integer exit code from the command, stdout as a string, stderr as a string
    """
    #print("execute command '%s'." % str(command))
    p = subprocess.Popen(command, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        if not hide_errors:
            print_tuple = p.returncode, str(command), stdout, stderr
            #print("command execution returned %d. Command: '%s', stdout: '%s', stderr: '%s'" % print_tuple)

    return p.returncode, stdout, stderr


def get_route_id_to_nexthop_dict():
    command = ["vtysh", "-c", "show bgp neighbors"]
    ret_code, out, err = run_command(command)
    if ret_code != 0:
        return {}

    try:
        filtered_out = []
        out = str(out, encoding = "utf-8")
        for line in out.split('\n'):
            if "BGP neighbor is " in line:
                filtered_out.append(line)
            if "remote router ID " in line:
                filtered_out.append(line)
            if "Nexthop: " in line:
                filtered_out.append(line)

        route_id_to_nexthop_dict = {}
        if len(filtered_out) % 3 == 0:
            for i in range(len(filtered_out)):
                if i%3 == 1:
                    route_id_to_nexthop_dict[filtered_out[i].split("remote router ID ")[1].split(',')[0].strip()] = {"nexthop" : filtered_out[i+1].split(":")[1].strip()}

        return route_id_to_nexthop_dict
    except:
        return {}

def get_local():
    global appl_db
    keys = appl_db.keys("NET_DETECT_STATUS*")
    keys = [ key.encode('utf-8') for key in keys]
    ips = [i[18:] for i in keys]
    delays = []
    resources = []
    for key in keys:
        net_status = appl_db.hgetall(key)
        if net_status:
            delays.append(net_status[u'delay'])
        else:
            delays.append(None)
        resource = appl_db.hgetall("COMPUTE_RESOURCE:{}".format(key[18:]))
        if resource:
            resources.append(resource)
        else:
            resources.append(None)

    # get router-id
    command = ["vtysh", "-c", "show running-config bgp"]
    ret_code, out, err = run_command(command)
    out = str(out)
    for line in out.split('\n'):
        if "bgp router-id" in line:
            router_id = line.split('router-id')[1].strip()
            break;
    else:
        router_id = "Unknown"

    # get nexthop from "ip route show"
    # 10.10.10.22 via 10.10.10.2 dev Ethernet2 proto 196 metric 20
    # ip is 10.10.10.2 then nh is 10.10.10.22
    nhs = []
    for ip in ips:
        command = ["ip","route","get",ip]
        ret_code, out, err = run_command(command)
        out = str(out)
        if ip in out:
            nhs.append(out.split("src ")[1].split(" ")[0].strip())
        else:
            nhs.append(None)

    res = []
    for i in range(len(ips)):
        if resources[i] and delays[i] and nhs[i]:
            res.append([router_id, ips[i], resources[i][u'cpu_num'].encode('utf-8'),resources[i][u'ephemeral_storage'].encode('utf-8'),resources[i][u'hugepages_1gi'].encode('utf-8'),resources[i][u'hugepages_2mi'].encode('utf-8'),resources[i][u'memory'].encode('utf-8'),resources[i][u'pods'].encode('utf-8'),delays[i].encode('utf-8'),nhs[i]])

    # [gw_ip,ip,cpu_num,ephemeral_storage,hugepages_1gi,hugepages_2mi,mem_size,pods,delay,nh]
    return res


def main():
    while True:
        comp_list = read_enhancedgw_from_file()
        parsed_list = []
        ## get nexthop
        #route_id_to_nexthop_dict = get_route_id_to_nexthop_dict()
        # parse
        try:
            for i in range(len(comp_list)):
                if comp_list[i].startswith("router-id"):
                    gw_ip = comp_list[i].split(' ')[1]
                    nh = comp_list[i].split(' ')[3]
                    remote_ip = comp_list[i].split(' ')[5]
                if comp_list[i].startswith("compute"):
                    ip = comp_list[i].split(' ')[1]
                    cpu_num = comp_list[i].split(' ')[2]
                    ephemeral_storage = comp_list[i].split(' ')[3]
                    hugepages_1gi = comp_list[i].split(' ')[4]
                    hugepages_2mi = comp_list[i].split(' ')[5]
                    mem_size = comp_list[i].split(' ')[6]
                    pods = comp_list[i].split(' ')[7]
                    net_status = appl_db.hgetall("NEIGHBOUR_DETECT_STATUS:{}".format(remote_ip))
                    if net_status and comp_list[i].split(' ')[8] != "forever" and net_status[u'delay'].encode('utf-8') != "forever":
                        delay = str(int(comp_list[i].split(' ')[8]) + int(net_status[u'delay'].encode('utf-8')))
                    else:
                        delay = "forever"

                    parsed_list.append([gw_ip,ip,cpu_num,ephemeral_storage,hugepages_1gi,hugepages_2mi,mem_size,pods,delay,nh])
        except:
            parsed_list = []
            time.sleep(3)
            continue

        # get local resources
        try:
            local = get_local()
        except:
            local = []
        if local:
            parsed_list.extend(local)

        # read from redis
        redis_list = get_compute_route()

        # judge which need to remove
        diff_list = find_in_A_not_in_B(redis_list, ["COMPUTE_ROUTE:"+i[0]+":"+i[1] for i in parsed_list])

        # for debug
        if (0):
            print(parsed_list)
            print(redis_list)
            print(diff_list)

        # set to redis
        for i in parsed_list:
            set_compute_route(i[0],i[1],i[2],i[3],i[4],i[5],i[6],i[7],i[8],i[9])

        # delete from redis
        for i in diff_list:
            delete_compute_route(i)

        # update every 3 seconds
        time.sleep(3)

if __name__ == "__main__":
    main()
