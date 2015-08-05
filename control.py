#!/usr/bin/env python

from sseclient import SSEClient
from Queue import Queue
import requests
import json
import threading
import socket
import sys
from text import Text

URL = 'https://robotman.firebaseIO.com/control/.json'

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
            msg = self.outbound_queue.get()
            if not msg:
                break
            to_post = json.dumps(msg)
            requests.post(URL, data=to_post)

    def close(self):
        self.outbound_queue.put(False)


class RemoteThread(threading.Thread):

    def __init__(self, message_queue):
        self.message_queue = message_queue
        super(RemoteThread, self).__init__()

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
                            self.message_queue.put(data[k])
                else:
                    # must be a push ID
                    self.message_queue.put(data)
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
            print 'incoming: %s' % (msg['text'])
            text_queue.put(msg)

    def close(self):
        self.inbound_queue.put(False)
        self.outbound_queue.put(False)
#        self.display_thread.join()

if __name__ == '__main__':
    args = sys.argv
    outbound_queue = Queue()
    inbound_queue = Queue()

    post_thread = PostThread(outbound_queue)
    post_thread.start()
    remote_thread = RemoteThread(inbound_queue)
    remote_thread.start()

    disp = Dispatcher(inbound_queue, outbound_queue)
    disp.run()

    post_thread.join()
    remote_thread.close()
    remote_thread.join()