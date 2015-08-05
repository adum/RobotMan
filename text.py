import threading
import sys
import curses

class Text(threading.Thread):

    def __init__(self, inbound_queue, outbound_queue):
        self.inbound_queue = inbound_queue
        self.outbound_queue = outbound_queue
        super(Text, self).__init__()

    def queue_text(self, text):
        packet = {'client': 'pi', 'text': text}
        self.outbound_queue.put(packet)

    def run(self):
        while True:
            msg = self.inbound_queue.get()
            if not msg:
                continue
            print 'text: %s' % (msg['text'])

    def close(self):
        self.outbound_queue.put(False)
