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

PHYSICAL_IFACE_PREFIX = ("eth", "ens", "enp", "eno")

def get_uptime():
    try:
        with open('/proc/uptime', 'r') as f:
            uptime = f.readline().split('.', 1)[0]
            return int(uptime)
    except:
        return 0

def get_memory():
    re_parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
    result = dict()
    try:
        for line in open('/proc/meminfo'):
            match = re_parser.match(line)
            if not match:
                continue
            key, value = match.groups()
            result[key] = int(value)

        MemTotal = float(result.get('MemTotal', 0))
        MemFree = float(result.get('MemFree', 0))
        Cached = float(result.get('Cached', 0))
        Buffers = float(result.get('Buffers', 0))
        # 更准确的已用内存计算
        MemUsed = MemTotal - (Cached + MemFree + Buffers)
        SwapTotal = float(result.get('SwapTotal', 0))
        SwapFree = float(result.get('SwapFree', 0))
        return int(MemTotal), int(MemUsed), int(SwapTotal), int(SwapFree)
    except:
        return 0, 0, 0, 0

def get_hdd():
    try:
        # 增加 --total 参数获取最后一行统计
        p = subprocess.check_output(['df', '-Tlm', '--total', '-t', 'ext4', '-t', 'ext3', '-t', 'ext2', '-t', 'reiserfs', '-t', 'jfs', '-t', 'ntfs', '-t', 'fat32', '-t', 'btrfs', '-t', 'fuseblk', '-t', 'zfs', '-t', 'simfs', '-t', 'xfs'], stderr=subprocess.STDOUT).decode("utf-8")
        total_line = p.splitlines()[-1]
        parts = total_line.split()
        size = parts[2]
        used = parts[3]
        return int(size), int(used)
    except:
        return 0, 0

def get_load():
    # 尝试兼容获取连接数
    try:
        # 简化了逻辑，直接通过命令行统计 ESTABLISHED 连接
        cmd = "netstat -an | grep ESTABLISHED | wc -l"
        tmp_load = os.popen(cmd).read().strip()
        return float(tmp_load)
    except:
        return 0.0

def get_time():
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
            time_list = line.split()[1:5] # 获取 user, nice, system, idle
            return [int(x) for x in time_list]
    except:
        return [0, 0, 0, 0]

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
    # t[3] 通常是 idle 时间
    result = 100 - (t[3] * 100.0 / st)
    return round(result)

class Traffic:
    def __init__(self):
        self.rx = collections.deque(maxlen=10)
        self.tx = collections.deque(maxlen=10)
    
    def get(self):
        try:
            with open('/proc/net/dev', 'r') as f:
                net_dev = f.readlines()
            
            avgrx = 0
            avgtx = 0

            for dev in net_dev[2:]:
                dev_parts = dev.split(':')
                if len(dev_parts) < 2: continue
                iface = dev_parts[0].strip()
                
                if not iface.startswith(PHYSICAL_IFACE_PREFIX):
                    continue
                
                data = dev_parts[1].split()
                avgrx += int(data[0])
                avgtx += int(data[8])

            self.rx.append(avgrx)
            self.tx.append(avgtx)

            if len(self.rx) < 2:
                return 0, 0

            # 计算平均速率
            diff_rx = self.rx[-1] - self.rx[0]
            diff_tx = self.tx[-1] - self.tx[0]
            
            # 这里的计算逻辑根据采样次数平滑
            period = (len(self.rx) - 1) * INTERVAL
            return int(diff_rx / period), int(diff_tx / period)
        except:
            return 0, 0

def liuliang():
    NET_IN = 0
    NET_OUT = 0
    try:
        with open('/proc/net/dev') as f:
            for line in f:
                if ":" not in line: continue
                iface, data = line.split(":")
                iface = iface.strip()
                if iface.startswith(PHYSICAL_IFACE_PREFIX):
                    parts = data.split()
                    NET_IN += int(parts[0])
                    NET_OUT += int(parts[8])
    except:
        pass
    return NET_IN, NET_OUT

def get_network(ip_version):
    host = "ipv4.google.com" if ip_version == 4 else "ipv6.google.com"
    try:
        socket.create_connection((host, 80), 2)
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
            
            # Python 3 接收的是 bytes，需要 decode
            data = s.recv(1024).decode('utf-8', 'ignore')
            
            if "Authentication required" in data:
                auth_str = USER + ':' + PASSWORD + '\n'
                s.send(auth_str.encode('utf-8'))
                data = s.recv(1024).decode('utf-8', 'ignore')
                if "Authentication successful" not in data:
                    print("Auth Failed:", data)
                    raise socket.error
            else:
                print("Unexpected Response:", data)
                raise socket.error

            # 继续读取握手后的协议信息
            data = s.recv(1024).decode('utf-8', 'ignore')
            
            check_ip = 0
            if "IPv4" in data:
                check_ip = 6
            elif "IPv6" in data:
                check_ip = 4
            else:
                raise socket.error("IP Check Protocol Error")

            traffic = Traffic()
            traffic.get()
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

                send_data = "update " + json.dumps(array) + "\n"
                s.send(send_data.encode('utf-8'))
                # 控制循环频率（get_cpu里已经有sleep了）
                
        except KeyboardInterrupt:
            print("Stopping...")
            break
        except socket.error as e:
            print("Disconnected... Error:", e)
            time.sleep(3)
        except Exception as e:
            print("Caught Exception:", e)
            time.sleep(3)
        finally:
            try:
                s.close()
            except:
                pass
