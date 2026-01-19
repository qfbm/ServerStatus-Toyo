# -*- coding: utf-8 -*-

SERVER = "127.0.0.1"
PORT = PORT
USER = "USER" 
PASSWORD = "USER_PASSWORD"
INTERVAL = 1 #更新间隔，单位：秒

import socket
import time
import re
import os
import json
import subprocess
import collections
import platform

def get_uptime():
    with open('/proc/uptime', 'r') as f:
        uptime = f.readline()
    uptime = uptime.split('.', 2)
    return int(uptime[0])

def get_memory():
    # 使用原始字符串 r'' 修复 SyntaxWarning
    re_parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
    result = dict()
    for line in open('/proc/meminfo'):
        match = re_parser.match(line)
        if not match:
            continue
        key, value = match.groups(['key', 'value'])
        result[key] = int(value)

    MemTotal = float(result.get('MemTotal', 0))
    MemFree = float(result.get('MemFree', 0))
    Cached = float(result.get('Cached', 0))
    MemUsed = MemTotal - (Cached + MemFree)
    SwapTotal = float(result.get('SwapTotal', 0))
    SwapFree = float(result.get('SwapFree', 0))
    return int(MemTotal), int(MemUsed), int(SwapTotal), int(SwapFree)

def get_hdd():
    try:
        p = subprocess.check_output(['df', '-Tlm', '--total', '-t', 'ext4', '-t', 'ext3', '-t', 'ext2', '-t', 'reiserfs', '-t', 'jfs', '-t', 'ntfs', '-t', 'fat32', '-t', 'btrfs', '-t', 'fuseblk', '-t', 'zfs', '-t', 'simfs', '-t', 'xfs']).decode("Utf-8")
        total = p.splitlines()[-1]
        used = total.split()[3]
        size = total.split()[2]
        return int(size), int(used)
    except:
        return 0, 0

def get_load():
    # 修复正则表达式警告并简化
    # 如果只是为了获取系统负载，os.getloadavg()[0] 是最标准做法
    # 这里保留原有的 netstat 逻辑但修复语法
    try:
        # 使用 r'' 修复转义
        cmd = "netstat -anp | grep ESTABLISHED | grep -E 'tcp|tcp6' | grep -E -o '([0-9]{1,3}[.]){3}[0-9]{1,3}' | sort -u | wc -l"
        tmp_load = os.popen(cmd).read().strip()
        return float(tmp_load) if tmp_load else 0.0
    except:
        return 0.0

def get_time():
    # Python 3 必须使用 open() 而不是 file()
    with open("/proc/stat", "r") as stat_file:
        time_list = stat_file.readline().split()[1:5] # 修正索引
    return [int(x) for x in time_list]

def delta_time():
    x = get_time()
    time.sleep(INTERVAL)
    y = get_time()
    for i in range(len(x)):
        y[i] -= x[i]
    return y

def get_cpu():
    t = delta_time()
    st = sum(t)
    if st == 0:
        st = 1
    # 最后一项通常是 idle time
    result = 100 - (t[3] * 100.0 / st)
    return round(result)

class Traffic:
    def __init__(self):
        self.rx = collections.deque(maxlen=10)
        self.tx = collections.deque(maxlen=10)
    def get(self):
        with open('/proc/net/dev', 'r') as f:
            net_dev = f.readlines()
        
        avgrx = 0; avgtx = 0
        for dev in net_dev[2:]:
            dev_split = dev.split(':')
            if len(dev_split) < 2: continue
            if dev_split[0].strip() == "lo" or "tun" in dev_split[0]:
                continue
            stats = dev_split[1].split()
            avgrx += int(stats[0])
            avgtx += int(stats[8])

        self.rx.append(avgrx)
        self.tx.append(avgtx)
        
        if len(self.rx) < 2: return 0, 0
        
        l = len(self.rx)
        diff_rx = self.rx[-1] - self.rx[0]
        diff_tx = self.tx[-1] - self.tx[0]
        
        return int(diff_rx / (l-1) / INTERVAL), int(diff_tx / (l-1) / INTERVAL)

def liuliang():
    NET_IN = 0
    NET_OUT = 0
    with open('/proc/net/dev') as f:
        for line in f:
            # 使用 r'' 修复 SyntaxWarning
            netinfo = re.findall(r'([^\s]+):[\s]{0,}(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', line)
            if netinfo:
                if netinfo[0][0] == 'lo' or 'tun' in netinfo[0][0] or netinfo[0][1]=='0':
                    continue
                NET_IN += int(netinfo[0][1])
                NET_OUT += int(netinfo[0][9])
    return NET_IN, NET_OUT

def get_network(ip_version):
    HOST = "ipv4.google.com" if ip_version == 4 else "ipv6.google.com"
    try:
        socket.create_connection((HOST, 80), 2)
        return True
    except:
        return False

if __name__ == '__main__':
    socket.setdefaulttimeout(30)
    while True:
        try:
            print("Connecting...")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER, PORT))
            
            # Python 3 需要 decode 接收到的数据
            data = s.recv(1024).decode('utf-8')
            if "Authentication required" in data:
                auth = USER + ':' + PASSWORD + '\n'
                s.send(auth.encode('utf-8')) # 需要 encode 为 bytes
                data = s.recv(1024).decode('utf-8')
                if "Authentication successful" not in data:
                    print(data)
                    raise socket.error
            else:
                print(data)
                raise socket.error

            data = s.recv(1024).decode('utf-8')
            check_ip = 0
            if "IPv4" in data:
                check_ip = 6
            elif "IPv6" in data:
                check_ip = 4
            else:
                raise socket.error

            traffic = Traffic()
            timer = 0
            while True:
                CPU = get_cpu()
                NetRx, NetTx = traffic.get()
                NET_IN, NET_OUT = liuliang()
                Uptime = get_uptime()
                Load = get_load()
                MemoryTotal, MemoryUsed, SwapTotal, SwapFree = get_memory()
                HDDTotal, HDDUsed = get_hdd()

                array = {}
                if timer <= 0:
                    array['online' + str(check_ip)] = get_network(check_ip)
                    timer = 10
                else:
                    timer -= INTERVAL

                array.update({
                    'uptime': Uptime,
                    'load': Load,
                    'memory_total': MemoryTotal,
                    'memory_used': MemoryUsed,
                    'swap_total': SwapTotal,
                    'swap_used': SwapTotal - SwapFree,
                    'hdd_total': HDDTotal,
                    'hdd_used': HDDUsed,
                    'cpu': CPU,
                    'network_rx': NetRx,
                    'network_tx': NetTx,
                    'network_in': NET_IN,
                    'network_out': NET_OUT
                })

                msg = "update " + json.dumps(array) + "\n"
                s.send(msg.encode('utf-8'))
        except KeyboardInterrupt:
            break
        except socket.error:
            print("Disconnected...")
            if 's' in locals(): s.close()
            time.sleep(3)
        except Exception as e:
            print("Caught Exception:", e)
            if 's' in locals(): s.close()
            time.sleep(3)
