#!/usr/local/bin python
# coding=utf-8

import optparse, sys, string, logging, time
import zabbix_api
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dateutil import tz 

class OptionClass:
    def __init__(self):
        self.user = None
        self.passwd = None

    def parse(self):
        option_list = [
            optparse.make_option("-u", "--user",
                        action="store", type="string", dest="user",
                        default="admin",
                        help="Zabbix login user name"),
            optparse.make_option("-p", "--passwd",
                        action="store", type="string", dest="passwd",
                        default="passwd",
                        help="Zabbix login user passwd"),
            optparse.make_option("-s", "--server",
                        action="store", type="string", dest="server",
                        default="http://localhost",
                        help="Zabbix server"),
            optparse.make_option("--hosts",
                        action="store", type="string", dest="hosts",
                        default="server1 server2...",
                        help="Monitor hosts"),
            optparse.make_option("-i", "--item",
                        action="store", type="string", dest="item",
                        default="gpu.avgutilization",
                        help="Monitor item"),
        ]

        self.parser = optparse.OptionParser(option_list=option_list)
        (options, _) = self.parser.parse_args()

        if options.user is not None:
            self.user = options.user 
        if options.passwd is not None:
            self.passwd = options.passwd
        if options.server is not None:
            self.server = options.server
        if options.hosts is not None:
            self.hosts = options.hosts.split(' ')
        if options.item is not None:
            self.item = options.item

    def validate(self):
        if self.user is None or self.passwd is None \
            or self.server is None or self.hosts is None or self.item is None:
            self.parser.print_help()
            sys.exit(1)
        logging.info("user:%s, passwd:%s, server:%s, hosts:%s, item:%s",
        self.user, self.passwd, self.server, str(self.hosts), self.item)

class ZabbixClient:
    def __init__(self, server="http://localhost"):
        self.zapi = zabbix_api.ZabbixAPI(server=server)

    def login(self, user="admin", passwd="passwd"):
        self.zapi.login(user, passwd)

    def logout(self):
        obj = self.zapi.json_obj('user.logout')
        result = self.zapi.do_request(obj)
        if 0 < len(result):
            res = result['result']
            logging.info("logout result:%s", res)

    def getHosts(self, host=[]):
        obj = self.zapi.json_obj(method='host.get', 
        params={'filter': {'host': host}})
        results = self.zapi.do_request(obj)
        hosts = [] 
        if 0 < len(results) and len(results['result']):
            for result in results['result']:
                host_map = {}
                host_map['host'] = result['host'] 
                host_map['hostid'] = result['hostid']
                hosts.append(host_map)

            return hosts
        return None

    def getItemID(self, hostid='', item='gpu.avgutilization'):
        obj = self.zapi.json_obj(method='item.get',
        params={'output': 'extend', 'hostids': hostid, 'search': {'key_': item}})
        results = self.zapi.do_request(obj)
        if 0 < len(results) and len(results['result']):
            return results['result'][0]['itemid']
        return None

    def getHistory(self, itemid='', time_from='', time_till=''):
        obj = self.zapi.json_obj(method='history.get',
        params={'output': 'extend', 'history': 0, 'itemids': itemid,
        'time_from': time_from, 'time_till': time_till,
        'sorfield': 'clock', 'sortorder': 'ASC'})
        results = self.zapi.do_request(obj)
        if 0 < len(results):
            return results['result']
        return None

def drawTimeDiagram(history_list):
    clock_list = []
    data_list = []

    for item in history_list[0]['item']:
        clock_list.append(int(item['clock']))

    for history in history_list:
        value_list = [] 
        for item in history['item']:
            value_list.append(float(item['value']))
        data = {}
        data['host'] = history['host']
        data['value'] = value_list

        data_list.append(data)

    df = pd.DataFrame()

    clock_series = pd.Series(clock_list)
    df['clock'] = clock_series
    df.clock = pd.to_datetime(df.clock, unit='s')

    for data in data_list:
        df[data['host']] = pd.Series(data['value']) 

    for history in history_list:
        plt.plot('clock', history['host'], data=df, label=history['host'])
    plt.legend()

    df.describe()

    plt.ylabel('GPU Avg Utilization')
    plt.xlabel('Time')

    xfmt = mdates.DateFormatter('%y-%m-%d %H:%M:%S', tz=tz.gettz('Asia/Shanghai'))
    plt.gca().xaxis.set_major_formatter(xfmt)

    plt.grid(True)
    plt.show()

def main():
    logging.basicConfig(filename='app.log', 
                        level=logging.INFO,
                        format='[%(asctime)s] %(process)s {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s')

    option = OptionClass()
    option.parse()
    option.validate()

    zabbixCli = ZabbixClient(server=option.server)

    try:
        zabbixCli.login(option.user, option.passwd)
    except zabbix_api.ZabbixAPIException as e:
        logging.error("Failed to login %s", str(e))
        return

    try:
        hosts = zabbixCli.getHosts(option.hosts)
    except zabbix_api.ZabbixAPIException as e:
        logging.error("Failed to get hosts id %s", str(e)) 
        return
    logging.info("hosts %s", str(hosts))

    time_now = str(time.time()).split('.')[0]
    time_from = str(int(time_now) - 7 * 24 * 60 * 60)

    history_list = [] 
    for host in hosts:
        try:
            itemID = zabbixCli.getItemID(hostid=host['hostid'], item=option.item)
        except zabbix_api.ZabbixAPIException as e:
            logging.error("Failed to get item %s", str(e))
            return
        logging.info("item is %s", itemID)
    
        if itemID is not None:
            try:
                '''
                export item data
                '''
                history = zabbixCli.getHistory(itemid=itemID, time_from=time_from, time_till=time_now)
            except zabbix_api.ZabbixAPIException as e:
                logging.error("Failed to get history %s", str(e))
                return
            logging.info("item is %s", str(history))
            history_map = {}
            history_map['host'] = host['host']
            history_map['item'] = history

            history_list.append(history_map)

    drawTimeDiagram(history_list)

    try:
        zabbixCli.logout()
    except zabbix_api.ZabbixAPIException as e:
        logging.error("Failed to logout %s", str(e))
        return

if __name__ == "__main__":
    main()