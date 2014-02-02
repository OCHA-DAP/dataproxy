#from google.appengine.ext.webapp.util import run_wsgi_app
import os
from app import JsonpDataProxy

application = JsonpDataProxy(3000000)


def _start_response(status, headers, exc_info=None):
	if exc_info is not None:
		raise exc_info[0], exc_info[1], exc_info[2]
	print "Status: %s" % status
	for name, val in headers:
		print "%s: %s" % (name, val)
	print
	return sys.stdout.write

def main():
    env = dict(os.environ)
    env["wsgi.input"] = sys.stdin
    env["wsgi.errors"] = sys.stderr
    env["wsgi.version"] = (1,0)
    env["wsgi.run_once"] = True
    env["wsgi.url_scheme"] = wsgiref.util.guess_scheme(env)
    env["msgi.multithread"] = False
    env["wsgi.multiprocess"] = False
    result = application(env, _start_response)
    try:
    	if result is not None:
    		for data in result:
    			sys.stdout.write(data)
    finally:
    	if hasattr(result, 'close'):
    		result.close()

if __name__ == "__main__":
    main()
