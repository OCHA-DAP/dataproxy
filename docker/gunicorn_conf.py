bind = '0.0.0.0:5000'
workers = 4
worker_class = 'gevent'
access_log_format = '"%({x-forwarded-for}i)s" %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
accesslog = '/var/log/dataproxy.access.log'
errorlog = '/var/log/dataproxy.error.log'
loglevel = 'warning'
#loglevel = 'debug'
