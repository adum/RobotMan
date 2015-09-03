#!/usr/bin/env python

from sseclient import SSEClient
from Queue import Queue
import requests
import json
import threading
import socket
import sys
import time
from text import Text
from pprint import pprint
from led.eyes import EyeChanger

BASE_DB = 'https://robotman.firebaseIO.com/'
DB = BASE_DB + 'control/'
URL = DB + '.json'

class ClosableSSEClient(SSEClient):
    """
    Hack in some closing functionality on top of the SSEClient
    """

    def __init__(self, *args, **kwargs):
        self.should_connect = True
        super(ClosableSSEClient, self).__init__(*args, **kwargs)

    def _connect(self):
        if self.should_connect:
            super(ClosableSSEClient, self)._connect()
        else:
            raise StopIteration()

    def close(self):
        self.should_connect = False
        self.retry = 0
        # HACK: dig through the sseclient library to the requests library down to the underlying socket.
        # then close that to raise an exception to get out of streaming. I should probably file an issue w/ the
        # requests library to make this easier
        self.resp.raw._fp.fp._sock.shutdown(socket.SHUT_RDWR)
        self.resp.raw._fp.fp._sock.close()

class PostThread(threading.Thread):

    def __init__(self, outbound_queue):
        self.outbound_queue = outbound_queue
        super(PostThread, self).__init__()

    def run(self):
        while True:
            post = self.outbound_queue.get()
#            pprint(post)
            url = DB + post['path'] + ".json"
            msg = post['msg']
            if not msg:
                break
            to_post = json.dumps(msg)
            print("posting url", url, to_post)
            requests.patch(url, data=to_post)
#            requests.post(url, data=to_post)

    def close(self):
        self.outbound_queue.put(False)


class RemoteThread(threading.Thread):

    def __init__(self, message_queue, outbound_queue):
        self.message_queue = message_queue
        self.outbound_queue = outbound_queue
        super(RemoteThread, self).__init__()

    def mark_processed(self, key):
#        self.outbound_queue.put({'path': key + "/processed/", 'msg': True})
        self.outbound_queue.put({'path': key, 'msg': {'processed': True}})

    def run(self):
        try:
            self.sse = ClosableSSEClient(URL)
            for msg in self.sse:
                msg_data = json.loads(msg.data)
                if msg_data is None:    # keep-alives
                    continue
                path = msg_data['path']
                data = msg_data['data']
                print "json:", msg.data
                if path == '/':
                    # initial update
                    if data:
                        keys = data.keys()
                        keys.sort()
                        for k in keys:
                            if not 'processed' in data[k]:
                                self.message_queue.put(data[k])
                                self.mark_processed(k)
                else:
                    # must be a push ID
                    self.message_queue.put(data)
                    if path.count("/") == 1: # not sub path
                        k = path.split("/")[1]
                        self.mark_processed(k)
        except socket.error:
            pass    # this can happen when we close the stream

    def close(self):
        if self.sse:
            self.sse.close()

class Dispatcher():

    def __init__(self, inbound_queue, outbound_queue):
        self.inbound_queue = inbound_queue
        self.outbound_queue = outbound_queue

    def queue_text(self, text):
        packet = {'client': 'pi', 'text': text}
        self.outbound_queue.put(packet)

    def run(self):
        text_queue = Queue()
        self.text = Text(text_queue, outbound_queue)
        self.text.start()
        while True:
            msg = self.inbound_queue.get()
            if not msg:
                break
            if not isinstance(msg, dict):
                continue
            if not 'text' in msg:
                continue # some child
#            print 'incoming: %s' % (msg['text'])
            if 'processed' in msg:
                print('already processed')
            else:
                text_queue.put(msg)
                

    def close(self):
        self.inbound_queue.put(False)
        self.outbound_queue.put(False)
#        self.display_thread.join()

def loadEyes():
    eye_changer = EyeChanger()
    try:
        url = BASE_DB + "pixels/.json"

        sse = SSEClient(url)
        for msg in sse:
#            print("data: " + str(len(msg.data)) + msg.data)
#            if len(msg.data) == 0:
#                continue
            msg_data = json.loads(msg.data)
            if msg_data is None:
                break
            path = msg_data['path']
            data = msg_data['data']
            print "pix json:", data
            for k, v in data.iteritems():
                print k, v
                eye_changer.eye_data(k, v)
            eye_changer.show_eye("eye")
            time.sleep(1.5)
            eye_changer.show_eye("eye_mid")
            time.sleep(1.5)
            eye_changer.show_eye("eye_shut")
            time.sleep(1.5)
            break
    except socket.error:
        pass    # this can happen when we close the stream
#    sse.close()

if __name__ == '__main__':
    args = sys.argv

    loadEyes()
    quit()

    print "starting threads"

    outbound_queue = Queue()
    inbound_queue = Queue()

    post_thread = PostThread(outbound_queue)
    post_thread.start()
    remote_thread = RemoteThread(inbound_queue, outbound_queue)
    remote_thread.start()

    # grabs items from inbound, sends them to handlers
    disp = Dispatcher(inbound_queue, outbound_queue)
    disp.run()

    post_thread.join()
    remote_thread.close()
    remote_thread.join()
