from zro import RemoteObject
from toolbox.IO.nidaq import DigitalInput

class DIServer(RemoteObject):
    def __init__(self):
        super(DIServer, self).__init__(rep_port=6500)
        self.di = DigitalInput("Dev3", port=0)

    def start(self):
        self.di.start()

    def stop(self):
        self.di.stop()

    def clear(self):
        self.di.clear()

    def read(self):
        return self.di.read()


def main():
    
    d = DIServer()
    d.run_forever()

if __name__ == '__main__':
    main()
