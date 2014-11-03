#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
################################################################################
#
# Copyright (c) 2009-2014 Alistek ( http://www.alistek.com ) All Rights Reserved.
#                    General contacts <info@alistek.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
################################################################################
from DocumentConverter import DocumentConverter, DocumentConversionException
from jsonrpc2 import JsonRpcException
import base64
from hashlib import md5
from random import randint
from os import path, rename, getpid
from time import time, sleep
import logging

MAXINT = 9223372036854775807

filters = {'pdf':'writer_pdf_Export', 'odt':'writer8', 'doc':'MS Word 97'}

class AccessException(Exception):
    pass
    
class NoidentException(Exception):
    pass

class NodataException(Exception):
    pass
    
class NoOfficeConnection(Exception):
    pass

class OfficeService():
    def __init__(self, oo_host, oo_port, spool_dir, auth_type):
        self.oo_host = oo_host
        self.oo_port = oo_port
        self.spool_path = spool_dir + '/%s'
        self.auth = auth_type
        self.init_conn()
    
    def init_conn(self):
        logger = logging.getLogger('main')
        try:
            self.oservice = DocumentConverter(self.oo_host, self.oo_port)
        except DocumentConversionException as e:
            self.oservice = None
            logger.warning("Failed to initiate OpenOffice/LibreOffice connection.")
    
    def conn_healthy(self):
        if self.oservice is not None:
            return True
        logger = logging.getLogger('main')
        attempt = 0
        while self.oservice is None and attempt < 3:
            attempt += 1
            self.init_conn()
            if self.oservice is not None:
                return True
            sleep(3)
        message = 'Failed to initiate connection to OpenOffice/LibreOffice three times in a row.'
        logger.warning(message)
        raise NoOfficeConnection(message)
    
    def convert(self, data=False, identifier=False, in_mime=False, out_mime=False, username=None, password=None):
        logger = logging.getLogger('main')
        if not self.auth(username, password):
            raise AccessException('Access denied.')
        start_time = time()
        logger.debug('Openning identifier: %s' % identifier)
        if data is not False:
            data = base64.b64decode(data)
        elif identifier is not False:
            with open(self.spool_path % self._md5(str(identifier)), "r") as tmpfile:
                data = tmpfile.read()
            data = base64.b64decode(data)
        else:
            raise NoidentException('Wrong or no identifier.')
        logger.debug("  read file %s" % str(time() - start_time))
        self.conn_healthy()
        self.oservice.putDocument(data)
        logger.debug("  upload document to office %s" % str(time() - start_time))
        conv_data = self.oservice.saveByStream(filters[out_mime or 'odt'])
        logger.debug("  download converted document %s" % str(time() - start_time))
        self.oservice.closeDocument()
        logger.debug("  close document %s" % str(time() - start_time))
        return base64.b64encode(conv_data).decode('utf8')

    def _md5(self, data):
        return md5(data.encode()).hexdigest()
        
    def upload(self, data=False, is_last=False, identifier=False, username=None, password=None):
        logger = logging.getLogger('main')
        logger.debug('Upload identifier: %s' % identifier)
        try:
            start_time = time()
            
            if not self.auth(username, password):
                raise AccessException('Access denied.')
            # NOTE:md5 conversion on file operations to prevent path injection attack
            if identifier and not path.isfile(self.spool_path % '_'+self._md5(str(identifier))):
                raise NoidentException('Wrong or no identifier.')
            elif data is False:
                raise NodataException('No data to be converted.')
            
            fname = ''
            # generate random identifier
            while not identifier:
                new_ident = randint(1, MAXINT)
                fname = self._md5(str(new_ident))
                logger.debug('  assigning new identifier %s' % new_ident)
                # check if there is any other such files
                identifier = not path.isfile(self.spool_path % '_'+fname) \
                             and not path.isfile(self.spool_path % fname) \
                             and new_ident or False
            fname = fname or self._md5(str(identifier))
            with open(self.spool_path % '_'+fname, "a") as tmpfile:
                tmpfile.write(data)
            logger.debug("  chunk finished %s" % str(time() - start_time))            
            if is_last:
                rename(self.spool_path % '_'+fname, self.spool_path % fname)
                logger.debug("  file finished")
            return {'identifier': identifier}
        except AccessException as e:
            raise e
        except NoidentException as e:
            raise e
        except NodataException as e:
            raise e
        except:
            import sys, traceback
            exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
            traceback.print_exception(exceptionType, exceptionValue,
            exceptionTraceback, limit=2, file=sys.stdout)
            
        
    def join(self, idents, out_mime=False, username=None, password=None):
        logger = logging.getLogger('main')
        logger.debug('Join %s identifiers: %s' % (str(len(idents)),str(idents)))
        if not self.auth(username, password):
            raise AccessException('Access denied.')
        start_time = time()
        ident = idents.pop(0)
        with open(self.spool_path % self._md5(str(ident)), "r") as tmpfile:
            data = tmpfile.read()
        data = base64.b64decode(data)
        try:
            self.conn_healthy()
            self.oservice.putDocument(data)
            data_list = []
            for ident in idents:
                with open(self.spool_path % self._md5(str(ident)), "r") as tmpfile:
                    data = tmpfile.read()
                data = base64.b64decode(data)
                data_list.append(data)
            self.oservice.joinDocuments(data_list)
            result_data = self.oservice.saveByStream(filters[out_mime or 'odt'])
            self.oservice.closeDocument()
        except:
            self.oservice.closeDocument()
        logger.debug("  join finished %s" % str(time() - start_time))
        return base64.b64encode(result_data).decode('utf8')
