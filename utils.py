import socket
def offline():
    try:
        socket.create_connection(("www.google.com", 80))
        return False
    except:
        pass
    return True