"""Data Proxy: a google app-engine application for proxying data to json (jsonp) format.
"""
import os
import logging
import httplib
import urlparse
import urllib2
import re

from cgi import FieldStorage
from StringIO import StringIO
try:
    import json
except ImportError:
    import simplejson as json

import sys
import os

def _add_vendor_packages():
    root = os.path.join(os.path.dirname(__file__), 'vendor')
    for vendor_package in os.listdir(root):
        path = os.path.join(root, vendor_package)
        if path in sys.path:
            continue
        sys.path.insert(1, path)
        # m = "adding %s to the sys.path: %s" % (vendor_package, sys.path)

_add_vendor_packages()

import dataconverters.commas
import dataconverters.xls

from bn import AttributeDict

log = logging.getLogger(__name__)


def render(**vars):
    return ["<html>\n"
        "<head>"
        "  <title>%(title)s</title>"
        "</head>\n"
        "<body>\n"
        "  <h1>%(title)s</h1>\n"
        "  <p>%(msg)s</p>\n"
        "</body>\n"
        "</html>\n" %vars
    ]

def error(**vars):
    return json.dumps(dict(error=vars), indent=4)

class ProxyError(StandardError):
    def __init__(self, title, message):
        super(ProxyError, self).__init__()
        self.title = title
        self.message = message
        self.error = "Error"

class ResourceError(ProxyError):
    def __init__(self, title, message):
        super(ResourceError, self).__init__(title, message)
        self.error = "Resource Error"

class RequestError(ProxyError):
    def __init__(self, title, message):
        super(RequestError, self).__init__(title, message)
        self.error = "Request Error"

class HTTPResponseMarble(object):
    def __init__(self, *k, **p):
        self.__dict__['status'] = u'200 OK'
        self.__dict__['status_format'] = u'unicode'
        self.__dict__['header_list'] = [dict(name=u'Content-Type', value=u'text/html; charset=utf8')]
        self.__dict__['header_list_format'] = u'unicode'
        self.__dict__['body'] = []
        self.__dict__['body_format'] = u'unicode'

    def __setattr__(self, name, value):
        if name not in self.__dict__:
            raise AttributeError('No such attribute %s'%name)
        self.__dict__[name] = value

class JsonpDataProxy(object):

    def __init__(self, max_length):
        self.max_length = int(max_length)

    def __call__(self, environ, start_response):
        # This is effectively the WSGI app.
        # Fake a pipestack setup so we cna port this code eventually
        flow = AttributeDict()
        flow['app'] = AttributeDict()
        flow['app']['config'] = AttributeDict()
        flow['app']['config']['proxy'] = AttributeDict(max_length=int(self.max_length))
        flow['environ'] = environ
        if not 'HTTP_COOKIE' in flow.environ:
            flow['environ']['HTTP_COOKIE'] = ''
        flow['http_response'] = HTTPResponseMarble()
        flow.http_response.header_list = [
            dict(name='Content-Type', value='application/javascript'),
            dict(name='Access-Control-Allow-Origin', value='*')
            ]
        flow['query'] = FieldStorage(environ=flow.environ)

        self.index(flow)

        start_response(
            str(flow.http_response.status),
            [tuple([item['name'], item['value']]) for item in flow.http_response.header_list],
        )
        resp  = ''.join([x.encode('utf-8') for x in flow.http_response.body])
        format = None

        if flow.query.has_key('format'):
            format = flow.query.getfirst('format')

        if not format or format == 'jsonp':
            callback = 'callback'
            if flow.query.has_key('callback'):
                callback = flow.query.getfirst('callback')
            return [callback+'('+resp+')']
        elif format == 'json':
            return [resp]
        else:
            title = 'Unknown reply format'
            msg = 'Reply format %s is not supported, try json or jsonp' % format
            flow.http_response.status = '200 Error %s' % title
            return error(title=title, message=msg)

    def index(self, flow):
        if not self.from_ckan(flow.environ['HTTP_COOKIE']):
            title = 'ckan only'
            msg = 'Dataproxy only accepts requests from CKAN installations'
            flow.http_response.status = '200 Error %s'%title
            flow.http_response.body = error(title=title, message=msg)
        elif not flow.query.has_key('url'):
            title = 'url query parameter missing'
            msg = 'Please read the dataproxy API format documentation: https://github.com/okfn/dataproxy'
            flow.http_response.status = '200 Error %s'%title
            flow.http_response.body = error(title=title, message=msg)
        else:
            url = flow.query.getfirst('url')

            try:
                self.proxy_query(flow, url, flow.query)
            except ProxyError, e:
                flow.http_response.status = '200 %s %s' % (e.error, e.title)
                flow.http_response.body = error(title=e.title, message=e.message)

    def from_ckan(self,cookies):
        #Checks to see if there's a ckan cookie present
        #for c in cookies.split(';'):
        #    t = c.split('=')
        #    if t[0].strip().lower() == 'ckan':
        #        return True
        #return False
        return True

    def proxy_query(self, flow, url, query):
        parts = urlparse.urlparse(url)

        # Get resource type - first try to see whether there is type= URL option,
        # if there is not, try to get it from file extension

        if parts.scheme not in ['http', 'https']:
            raise ResourceError('Only HTTP URLs are supported',
                                'Data proxy does not support %s URLs' % parts.scheme)

        resource_type = query.getfirst("type")
        if not resource_type:
            resource_type = os.path.splitext(parts.path)[1]

        if not resource_type:
            raise RequestError('Could not determine the resource type',
                                'If file has no type extension, specify file type in type= option')

        resource_type = re.sub(r'^\.', '', resource_type.lower())

        max_results = 500
        if "max-results" in query:
            try:
                max_results = int(query.getfirst("max-results"))
            except:
                raise ValueError("max-results should be an integer")

        try:
            records, metadata = transform(resource_type, flow, url, query, max_results)
        except Exception, e:
            log.debug('Transformation of %s failed. %s: %s', url, e.__class__.__name__, e)
            raise ResourceError("Data Transformation Error",
                                "Data transformation failed. %s: %s" % (e.__class__.__name__, e))

        fields = [ f['id'] for f in metadata['fields'] ]
        data = []
        for count, r in enumerate(records):
            if count >= max_results:
                break
            data.append([ r[field] for field in fields ])

        result = {
            'url': url,
            'data': data,
            'metadata': metadata,
            'fields': fields
        }

        if query.has_key('indent'):
            indent=int(query.getfirst('indent'))
        else:
            indent=None

        flow.http_response.body = json.dumps(result, indent=indent,
                cls=OurEncoder)


import datetime
import decimal
class OurEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)


def transform(type_name, flow, url, query, max_results):
    # window size is the number of rows that are pre-fetched and analysed
    window = min(max_results, 256)
    encoding = None
    guess_types = True
    if 'guess-types' in query:
        guess_types = query['guess-types'].lower() in ('yes', 'true', '1', 't', 'enabled')
    if 'encoding' in query:
        encoding = query["encoding"].value
    if type_name == 'csv':
        stream = create_stream(flow, url)
        records, metadata = dataconverters.commas.parse(stream, encoding=encoding,
                window=window, guess_types=guess_types)
    elif type_name == 'tsv':
        stream = create_stream(flow, url)
        records, metadata = dataconverters.commas.parse(stream, delimiter='\t',
                encoding=encoding, window=window, guess_types=guess_types)
    elif type_name == 'xls' or type_name == 'xlsx':
        stream = create_stream(flow, url)
        length = int(stream.headers.get('content-length', 0))
        # max_length = flow.app.config.proxy.max_length
        max_length = 5000000 # ~ 5Mb
        if length and length > max_length:
            raise ResourceError('The requested file is too big to proxy',
                                'Requested resource is %s bytes. Size limit is %s. '
                                'If we proxy large files we\'ll use up all our bandwidth'
                                % (length, max_length))
        if 'worksheet' in query:
            sheet_number = max(int(query.getfirst('worksheet')), 1)
        else:
            sheet_number = 1
        records, metadata = dataconverters.xls.parse(stream,
                excel_type=type_name,
                guess_types=guess_types)
    else:
        raise Exception("Resource type not supported '%s'" % type_name)
    return (records, metadata)

def from_hdx(url):
    url = urlparse.urlparse(url)
    # url = url.netloc.split(':')
    if url.netloc.endswith(('data.humdata.org', 'data.humdata.local')):
        return True
    else:
        return False

def create_stream(flow, url):
    hdx = from_hdx(url)
    if hdx:
        request = urllib2.Request(url, headers={"Cookie" : flow.environ['HTTP_COOKIE'], 'User-Agent': os.getenv('HDX_USER_AGENT','HDXINTERNAL_DATAPROXY')})
        try:
            stream = urllib2.urlopen(request)
        except urllib2.HTTPError, err:
            if err.code == 403:
                raise Exception("You do not have permission to access this file.")
            else:
                if hdx:
                    raise Exception("File could not be fetched from filestore.")
                else:
                    raise Exception("File could not be fetched.")
    else:
        stream = urllib2.urlopen(url)
    return stream

if __name__ == '__main__':
    from wsgiref.util import setup_testing_defaults
    from wsgiref.simple_server import make_server

    logging.basicConfig(level=logging.DEBUG)
    httpd = make_server('', 8000, JsonpDataProxy(100000))
    print "Serving on port 8000..."
    httpd.serve_forever()
