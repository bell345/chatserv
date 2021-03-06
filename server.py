#!/usr/bin/env python3

import socket
import threading
import time
import logging
import sys

HOST = ''
PORT = 8018
TIMEOUT = 5
BUF_SIZE = 1024

from util import safe_send, string_t

class WhatsUpServer(threading.Thread):

    def __init__(self, conn, addr):
        threading.Thread.__init__(self)
        self.conn = conn
        self.addr = addr
        self.ip = self.addr[0]
        self.name = ''

    def print_indicator(self, prompt):
        string_t("{0}\n>> ".format(prompt)).send(self.conn)

    def login(self):
        global clients
        global messages
        global accounts
        global onlines

        logging.info('Connected from: %s:%s' %
                     (self.addr[0], self.addr[1]))
        clients.add((self.conn, self.addr))
        msg = '\n## Welcome to WhatsUp\n## Enter `!q` to quit\n'

        # new user
        print('accounts')
        if self.ip not in accounts:
            msg += '## Please enter your name:'
            self.print_indicator(msg)
            accounts[self.ip] = {
                'name': '',
                'pass': '',
                'lastlogin': time.ctime()
            }
            while 1:
                name = string_t.recv(self.conn).strip()
                if name in messages:
                    self.print_indicator(
                        '## This name already exists, please try another')
                else:
                    break
            accounts[self.ip]['name'] = name
            self.name = name
            logging.info('%s logged as %s' % (self.addr[0], self.name))
            messages[name] = []
            self.print_indicator(
                '## Hello %s, please enter your password:' % (self.name,))
            password = string_t.recv(self.conn).strip()
            accounts[self.ip]['pass'] = password
            self.print_indicator('## Welcome, enjoy your chat')
        else:
            self.name = accounts[self.ip]['name']
            msg += '## Hello %s, please enter your password:' % (self.name,)
            # print accounts
            self.print_indicator(msg)
            while 1:
                password = string_t.recv(self.conn).strip()
                if password != accounts[self.ip]['pass']:
                    self.print_indicator(
                        '## Incorrect password, please enter again')
                else:
                    self.print_indicator(
                        '## Welcome back, last login: %s' %
                        (accounts[self.ip]['lastlogin'],))
                    accounts[self.ip]['lastlogin'] = time.ctime()
                    break
            string_t(self.show_mentions(self.name)).send(self.conn)
        self.broadcast('`%s` is online now' % (self.name,), clients, False)
        onlines[self.name] = self.conn

    def logoff(self):
        global clients
        global onlines
        string_t('## Bye!\n').send(self.conn)
        del onlines[self.name]
        clients.remove((self.conn, self.addr))
        if onlines:
            self.broadcast('## `%s` is offline now' %
                           (self.name,), clients)
        self.conn.close()
        exit()

    def check_keyword(self, buf):
        global onlines

        if buf.find('!q') == 0:
            self.logoff()

        if buf.find('#') == 0:
            group_keyword = buf.split(' ')[0][1:]
            group_component = group_keyword.split(':')

            # to post in a group
            if len(group_component) == 1:
                group_name = group_component[0]
                try:
                    msg = '[%s]%s: %s' % (
                        group_name, self.name, buf.split(' ', 1)[1])
                    self.group_post(group_name, msg)
                except IndexError:
                    self.print_indicator(
                        '## What do you want to do with `#%s`?' % (group_name))

            # to join / leave a group
            elif len(group_component) == 2:
                group_name = group_component[0]
                if group_component[1] == 'join':
                    self.group_join(group_name)
                elif group_component[1] == 'leave':
                    self.group_leave(group_name)
            return True

        if buf.find('@') == 0:
            to_user = buf.split(' ')[0][1:]
            from_user = self.name
            msg = buf.split(' ', 1)[1]

            # if user is online
            if to_user in onlines:
                string_t('@%s: %s\n>> ' % (from_user, msg)).send(onlines[to_user])
                self.mention(from_user, to_user, msg, 1)
            # offline
            else:
                self.mention(from_user, to_user, msg)
            return True

    def group_post(self, group_name, msg):
        global groups
        # if the group does not exist, create it
        groups.setdefault(group_name, set())

        # if current user is a member of the group
        if (self.conn, self.addr) in groups[group_name]:
            self.broadcast(msg, groups[group_name])
        else:
            self.print_indicator(
                '## You are current not a member of group `%s`' % (group_name,))

    def group_join(self, group_name):
        global groups
        groups.setdefault(group_name, set())
        groups[group_name].add((self.conn, self.addr))
        self.print_indicator('## You have joined the group `%s`' %
                             (group_name,))

    def group_leave(self, group_name):
        global groups
        try:
            groups[group_name].remove((self.conn, self.addr))
            self.print_indicator('## You have left the group `%s`' %
                                 (group_name,))
        except:
            pass
        #except KeyboardInterrupt:
        #    print('Quited')
        #    sys.exit(0)
        #except Exception as e:
        #    pass

    def mention(self, from_user, to_user, msg, read=0):
        global messages
        # print 'Messages', messages
        if to_user in messages:
            messages[to_user].append([from_user, msg, read])
            self.print_indicator('## Message has sent to %s' % (to_user,))
        else:
            self.print_indicator('## No such user named `%s`' % (to_user,))

    def show_mentions(self, name):
        global messages
        res = '## Here are your messages:\n'
        if not messages[name]:
            res += '   No messages available\n>> '
            return res
        for msg in messages[name]:
            if msg[2] == 0:
                res += '(NEW) %s: %s\n' % (msg[0], msg[1])
                msg[2] = 1
            else:
                res += '      %s: %s\n' % (msg[0], msg[1])
        res += '>> '
        return res

    def broadcast(self, msg, receivers, to_self=True):
        for conn, addr in receivers:
            # if the client is not the current user
            if addr[0] != self.ip:
                string_t(msg + '\n>> ').send(conn)
            # if current user
            elif to_self:
                string_t('>> ').send()

    def run(self):
        global messages
        global accounts
        global clients
        self.login()

        try:
            while 1:
                self.conn.settimeout(TIMEOUT)
                buf = string_t.recv(self.conn).strip()
                logging.info('%s@%s: %s' % (self.name, self.addr[0], buf))
                # check features
                if not self.check_keyword(buf):
                    # client broadcasts message to all
                    self.broadcast('%s: %s' % (self.name, buf), clients)

        except KeyboardInterrupt:
            print('Quited')
            sys.exit(0)
        except Exception as e:
            # timed out
            pass

def main():
    global clients
    global messages
    global accounts
    global onlines
    global groups

    # logging setup
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s: %(message)s',
                        datefmt='%d/%m/%Y %I:%M:%S %p')

    # initialize global vars
    clients = set()
    messages = {}
    accounts = {}
    onlines = {}
    groups = {}

    # set up socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(5)
    print ('-= WhatsUp Server =-')
    print ('>> Listening on:'), PORT
    print (PORT)

    while 1:
        conn, addr = sock.accept()
        server = WhatsUpServer(conn, addr)
        server.start()

if __name__ == '__main__':
    main()
