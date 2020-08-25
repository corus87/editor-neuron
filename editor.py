# -*- coding: iso-8859-1 -*-
# Based on https://github.com/danielperna84/hass-configurator
# Modified and changed for the use for Kalliope

from kalliope.core.NeuronModule import NeuronModule, MissingParameterException
from kalliope.core.Cortex import Cortex
from kalliope import Utils

import os
import sys
import cgi
import json
import time
import fnmatch
import mimetypes
import threading
import socketserver

from string import Template
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

WORKING_DIR = os.path.dirname(os.path.realpath(__file__))
IGNORE_PATTERN = []
DIRSFIRST = False
HIDEHIDDEN = False
PAGE_TITLE = None
BASEDIR = "."

class Editor(NeuronModule):
    def __init__(self, **kwargs):
        super(Editor, self).__init__(**kwargs)
        # the args from the neuron configuration
        listen_ip = kwargs.get('listen_ip', '0.0.0.0')
        port = kwargs.get('port', 8000)
        ignore_pattern = kwargs.get('ignore_pattern', None)
        dir_first = kwargs.get('dir_first', False)
        hide_hidden = kwargs.get('hide_hidden', False)
        page_title = kwargs.get('page_title', "Kalliope Editor")
        stop_server = kwargs.get('stop_server', False)

        if stop_server:
            self.stop_http_server()
            Utils.print_info("[ Editor ] Editor stopped")
        else:
            global IGNORE_PATTERN, DIRSFIRST, HIDEHIDDEN, PAGE_TITLE

            IGNORE_PATTERN = ignore_pattern
            DIRSFIRST = dir_first
            HIDEHIDDEN = hide_hidden
            PAGE_TITLE = page_title
            
            if self.stop_http_server():
                server = EditorThread(listen_ip, int(port))
                server.daemon = True
                server.start()
                Cortex.save('EditorServerThread', server)

    def stop_http_server(self):
        running_server = Cortex.get_from_key("EditorServerThread")
        if running_server:
            Utils.print_info("[ Editor ] Editor is running, stopping now...")
            running_server.shutdown_server()
            while not running_server.is_down:
                time.sleep(0.1)
        return True

class EditorThread(threading.Thread):
    def __init__(self, listen_ip, port):
        super(EditorThread, self).__init__()
        self.is_down = False
        server_address = (listen_ip, port)
        self.httpd = SimpleServer(server_address, RequestHandler)
        Utils.print_info(('[ Editor ] Listening on: http://%s:%s') % (self.httpd.server_address[0], self.httpd.server_address[1]))
        
    def run(self):
        self.httpd.serve_forever()

    def shutdown_server(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.is_down = True

def is_safe_path(basedir, path, follow_symlinks=True):
    """Check path for malicious traversal."""
    if basedir is None:
        return True
    if follow_symlinks:
        return os.path.realpath(path).startswith(basedir.encode('utf-8'))
    return os.path.abspath(path).startswith(basedir.encode('utf-8'))

def get_dircontent(path):
    """Get content of directory."""
    dircontent = []
    def sorted_file_list():
        """Sort list of files / directories."""
        dirlist = [x for x in os.listdir(path) if os.path.isdir(os.path.join(path, x))]
        filelist = [x for x in os.listdir(path) if not os.path.isdir(os.path.join(path, x))]
        if HIDEHIDDEN:
            dirlist = [x for x in dirlist if not x.startswith('.')]
            filelist = [x for x in filelist if not x.startswith('.')]
        if DIRSFIRST:
            return sorted(dirlist, key=lambda x: x.lower()) + \
                sorted(filelist, key=lambda x: x.lower())
        return sorted(dirlist + filelist, key=lambda x: x.lower())

    for elem in sorted_file_list():
        edata = {}
        edata['name'] = elem
        edata['dir'] = path
        edata['fullpath'] = os.path.abspath(os.path.join(path, elem))
        edata['type'] = 'dir' if os.path.isdir(edata['fullpath']) else 'file'
        try:
            stats = os.stat(os.path.join(path, elem))
            edata['size'] = stats.st_size
            edata['modified'] = stats.st_mtime
            edata['created'] = stats.st_ctime
        except Exception:
            edata['size'] = 0
            edata['modified'] = 0
            edata['created'] = 0

        hidden = False
        if IGNORE_PATTERN is not None:
            for file_pattern in IGNORE_PATTERN:
                if fnmatch.fnmatch(edata['name'], file_pattern):
                    hidden = True

        if not hidden:
            dircontent.append(edata)
    return dircontent

def get_html():
    """Load the HTML from file in dev-mode, otherwise embedded."""
    with open(WORKING_DIR + "/index.html") as file:
        return Template(file.read())


class RequestHandler(BaseHTTPRequestHandler):
    """Request handler."""
    
    def log_message(self, format, *args):
        return

    def do_BLOCK(self, status=420, reason="Policy not fulfilled"):
        """Customized do_BLOCK method."""
        self.send_response(status)
        self.end_headers()
        self.wfile.write(bytes(reason, "utf8"))

    def do_GET(self):
        """Customized do_GET method."""
        req = urlparse(self.path)
        query = parse_qs(req.query)
        self.send_response(200)
        if req.path.endswith('/api/file'):
            content = ""
            filename = query.get('filename', None)
            try:
                if filename:
                    is_raw = False
                    filename = unquote(filename[0]).encode('utf-8')
                    filepath = os.path.join(BASEDIR.encode('utf-8'), filename)
                    if os.path.isfile(filepath):
                        mimetype = mimetypes.guess_type(filepath.decode('utf-8'))
                        if mimetype[0] is not None:
                            if mimetype[0].split('/')[0] == 'image':
                                is_raw = True
                        if is_raw:
                            with open(filepath, 'rb') as fptr:
                                content = fptr.read()
                            self.send_header('Content-type', mimetype[0])
                        else:
                            with open(filepath, 'rb') as fptr:
                                content += fptr.read().decode('utf-8')
                            self.send_header('Content-type', 'text/text')
                    else:
                        self.send_header('Content-type', 'text/text')
                        content = "File not found"
            except Exception as err:
                self.send_header('Content-type', 'text/text')
                content = str(err)
            self.end_headers()
            if is_raw:
                self.wfile.write(content)
            else:
                self.wfile.write(bytes(content, "utf8"))
            return
        elif req.path.endswith('/api/download'):
            content = ""
            filename = query.get('filename', None)
            try:
                if filename:
                    filename = unquote(filename[0]).encode('utf-8')
                    if os.path.isfile(os.path.join(BASEDIR.encode('utf-8'), filename)):
                        with open(os.path.join(BASEDIR.encode('utf-8'), filename), 'rb') as fptr:
                            filecontent = fptr.read()
                        self.send_header(
                            'Content-Disposition',
                            'attachment; filename=%s' % filename.decode('utf-8').split(os.sep)[-1])
                        self.end_headers()
                        self.wfile.write(filecontent)
                        return
                    content = "File not found"
            except Exception as err:
                content = str(err)
            self.send_header('Content-type', 'text/text')
            self.wfile.write(bytes(content, "utf8"))
            return
        elif req.path.endswith('/api/listdir'):
            content = {'error': None}
            self.send_header('Content-type', 'text/json')
            self.end_headers()
            dirpath = query.get('path', None)
            try:
                if dirpath:
                    dirpath = unquote(dirpath[0]).encode('utf-8')
                    if os.path.isdir(dirpath):
                        activebranch = None
                        dirty = False
                        dircontent = get_dircontent(dirpath.decode('utf-8'))

                        filedata = {
                            'content': dircontent,
                            'abspath': os.path.abspath(dirpath).decode('utf-8'),
                            'parent': os.path.dirname(os.path.abspath(dirpath)).decode('utf-8'),
                            'activebranch': activebranch,
                            'dirty': dirty,
                            'error': None
                        }
                        self.wfile.write(bytes(json.dumps(filedata), "utf8"))
            except Exception as err:
                content['error'] = str(err)
                self.wfile.write(bytes(json.dumps(content), "utf8"))
            return
        elif req.path.endswith('/api/abspath'):
            content = ""
            self.send_header('Content-type', 'text/text')
            self.end_headers()
            dirpath = query.get('path', None)
            if dirpath:
                dirpath = unquote(dirpath[0]).encode('utf-8')
                absp = os.path.abspath(dirpath)
                if os.path.isdir(dirpath):
                    self.wfile.write(os.path.abspath(dirpath))
            return
        elif req.path.endswith('/api/parent'):
            content = ""
            self.send_header('Content-type', 'text/text')
            self.end_headers()
            dirpath = query.get('path', None)
            if dirpath:
                dirpath = unquote(dirpath[0]).encode('utf-8')
                absp = os.path.abspath(dirpath)
                if os.path.isdir(dirpath):
                    self.wfile.write(os.path.abspath(os.path.dirname(dirpath)))
            return

        elif req.path.endswith('/'):
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = get_html().safe_substitute(
                separator="\%s" % os.sep if os.sep == "\\" else os.sep,
                page_title=PAGE_TITLE)
            self.wfile.write(bytes(html, "utf8"))
            return
        elif req.path.endswith(('.css', '.eot', 'ttf', '.woff', 'woff2', '.js')):
            path = WORKING_DIR + req.path
            filepath = path.lstrip("/")
            f = open(os.path.join('.', path), "rb")
            mimetype, _ = mimetypes.guess_type(filepath)
            self.send_header('Content-type', mimetype)
            self.end_headers()
            for s in f:
                self.wfile.write(s)
            return
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(bytes("File not found", "utf8"))

    def do_POST(self):
        """Customized do_POST method."""
        req = urlparse(self.path)

        response = {
            "error": True,
            "message": "Generic failure"
        }

        length = int(self.headers['content-length'])
        if req.path.endswith('/api/save'):
            try:
                postvars = parse_qs(self.rfile.read(length).decode('utf-8'),
                                    keep_blank_values=1)
            except Exception as err:
                response['message'] = "%s" % (str(err))
                postvars = {}
            if 'filename' in postvars.keys() and 'text' in postvars.keys():
                if postvars['filename'] and postvars['text']:
                    try:
                        filename = unquote(postvars['filename'][0])
                        response['file'] = filename
                        with open(filename, 'wb') as fptr:
                            fptr.write(bytes(postvars['text'][0], "utf-8"))
                        self.send_response(200)
                        self.send_header('Content-type', 'text/json')
                        self.end_headers()
                        response['error'] = False
                        response['message'] = "File saved successfully"
                        self.wfile.write(bytes(json.dumps(response), "utf8"))
                        return
                    except Exception as err:
                        response['message'] = "%s" % (str(err))
            else:
                response['message'] = "Missing filename or text"
        elif req.path.endswith('/api/upload'):
            if length > 104857600: #100 MB for now
                read = 0
                while read < length:
                    read += len(self.rfile.read(min(66556, length - read)))
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                response['error'] = True
                response['message'] = "File too big: %i" % read
                self.wfile.write(bytes(json.dumps(response), "utf8"))
                return
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['Content-Type'],
                })
            filename = form['file'].filename
            filepath = form['path'].file.read()
            data = form['file'].file.read()
            open("%s%s%s" % (filepath, os.sep, filename), "wb").write(data)
            self.send_response(200)
            self.send_header('Content-type', 'text/json')
            self.end_headers()
            response['error'] = False
            response['message'] = "Upload successful"
            self.wfile.write(bytes(json.dumps(response), "utf8"))
            return
        elif req.path.endswith('/api/rename'):
            try:
                postvars = parse_qs(self.rfile.read(length).decode('utf-8'),
                                    keep_blank_values=1)
            except Exception as err:
                response['message'] = "%s" % (str(err))
                postvars = {}
            if 'src' in postvars.keys() and 'dstfilename' in postvars.keys():
                if postvars['src'] and postvars['dstfilename']:
                    try:
                        src = unquote(postvars['src'][0])
                        dstfilename = unquote(postvars['dstfilename'][0])
                        renamepath = src[:src.index(os.path.basename(src))] + dstfilename
                        response['path'] = renamepath
                        try:
                            os.rename(src, renamepath)
                            self.send_response(200)
                            self.send_header('Content-type', 'text/json')
                            self.end_headers()
                            response['error'] = False
                            response['message'] = "Rename successful"
                            self.wfile.write(bytes(json.dumps(response), "utf8"))
                            return
                        except Exception as err:
                            response['error'] = True
                            response['message'] = str(err)

                    except Exception as err:
                        response['message'] = "%s" % (str(err))
            else:
                response['message'] = "Missing filename or text"
        elif req.path.endswith('/api/delete'):
            try:
                postvars = parse_qs(self.rfile.read(length).decode('utf-8'),
                                    keep_blank_values=1)
            except Exception as err:
                response['message'] = "%s" % (str(err))
                postvars = {}
            if 'path' in postvars.keys():
                if postvars['path']:
                    try:
                        delpath = unquote(postvars['path'][0])
                        response['path'] = delpath
                        try:
                            if os.path.isdir(delpath):
                                os.rmdir(delpath)
                            else:
                                os.unlink(delpath)
                            self.send_response(200)
                            self.send_header('Content-type', 'text/json')
                            self.end_headers()
                            response['error'] = False
                            response['message'] = "Deletion successful"
                            self.wfile.write(bytes(json.dumps(response), "utf8"))
                            return
                        except Exception as err:
                            response['error'] = True
                            response['message'] = str(err)

                    except Exception as err:
                        response['message'] = "%s" % (str(err))
            else:
                response['message'] = "Missing filename or text"
        elif req.path.endswith('/api/newfolder'):
            try:
                postvars = parse_qs(self.rfile.read(length).decode('utf-8'),
                                    keep_blank_values=1)
            except Exception as err:
                response['message'] = "%s" % (str(err))
                postvars = {}
            if 'path' in postvars.keys() and 'name' in postvars.keys():
                if postvars['path'] and postvars['name']:
                    try:
                        basepath = unquote(postvars['path'][0])
                        name = unquote(postvars['name'][0])
                        response['path'] = os.path.join(basepath, name)
                        try:
                            os.makedirs(response['path'])
                            self.send_response(200)
                            self.send_header('Content-type', 'text/json')
                            self.end_headers()
                            response['error'] = False
                            response['message'] = "Folder created"
                            self.wfile.write(bytes(json.dumps(response), "utf8"))
                            return
                        except Exception as err:
                            response['error'] = True
                            response['message'] = str(err)
                    except Exception as err:
                        response['message'] = "%s" % (str(err))
        elif req.path.endswith('/api/newfile'):
            try:
                postvars = parse_qs(self.rfile.read(length).decode('utf-8'),
                                    keep_blank_values=1)
            except Exception as err:
                response['message'] = "%s" % (str(err))
                postvars = {}
            if 'path' in postvars.keys() and 'name' in postvars.keys():
                if postvars['path'] and postvars['name']:
                    try:
                        basepath = unquote(postvars['path'][0])
                        name = unquote(postvars['name'][0])
                        response['path'] = os.path.join(basepath, name)
                        try:
                            with open(response['path'], 'w') as fptr:
                                fptr.write("")
                            self.send_response(200)
                            self.send_header('Content-type', 'text/json')
                            self.end_headers()
                            response['error'] = False
                            response['message'] = "File created"
                            self.wfile.write(bytes(json.dumps(response), "utf8"))
                            return
                        except Exception as err:
                            response['error'] = True
                            response['message'] = str(err)
                    except Exception as err:
                        response['message'] = "%s" % (str(err))
            else:
                response['message'] = "Missing filename or text"
        else:
            response['message'] = "Invalid method"
        self.send_response(200)
        self.send_header('Content-type', 'text/json')
        self.end_headers()
        self.wfile.write(bytes(json.dumps(response), "utf8"))
        return
        
class SimpleServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Server class."""
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, server_address, RequestHandlerClass):
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)
