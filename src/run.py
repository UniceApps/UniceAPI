from waitress import serve
import __init__ as UniceAPI

serve(UniceAPI.app, port=5000, url_scheme='https')