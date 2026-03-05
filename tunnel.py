from pyngrok import ngrok
import time

ngrok.set_auth_token('3AXZthihCU33aoUzKnJH3DiaiTS_6mrLEnMi8XhdpzZNfge2i')
tunnel = ngrok.connect(8000)
print(f'Tunnel activo: {tunnel.public_url}/webhook')
print('Ctrl+C para cerrar')

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    ngrok.disconnect(tunnel.public_url)
    print('Tunnel cerrado.')
