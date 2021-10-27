#***************************************************************************
#*   (c) Benjamin Alterauge (gift) 2021                                    *   
#*                                                                         *
#*   This file is part of the FreeCAD CAx development system.              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   FreeCAD is distributed in the hope that it will be useful,            *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Lesser General Public License for more details.                   *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with FreeCAD; if not, write to the Free Software        *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

# e57importer, a FreeCAD Library
# Simple lib to import e57 data 

# infos:
# http://www.libe57.org
# http://paulbourke.net/dataformats/e57/

import numpy as np


E57_DEBUG        = True

E57_NS = {'e57':'http://www.astm.org/COMMIT/E57/2010-e57-v1.0'}
E57_PAGE_CRC     = 4
E57_STD_PAGE_SIZE = 1024
E57_COMPRESSED_VECTOR_SECTION = 1
E57_INDEX_PACKET = 0
E57_DATA_PACKET  = 1
E57_EMPTY_PACKET = 2 
E57_DATA_PACKET_MAX = (64*E57_STD_PAGE_SIZE)

class E57:

    def __init__(self, filename, checkfile=True): 
        self.filename  = filename
        self.checkfile = checkfile 
        self.readHeader()
        self.buildRoot()
        
    def readHeader(self):
        header = E57Header(self.filename)
        self.fileSignature      = header['fileSignature'].decode()
        self.majorVersion       = header['majorVersion']
        self.minorVersion       = header['minorVersion']
        self.filePhysicalLength = header['filePhysicalLength']
        self.xmlPhysicalOffset  = header['xmlPhysicalOffset']
        self.xmlLogicalLength   = header['xmlLogicalLength']
        self.pageSize           = header['pageSize']
        self.pageContent        = (self.pageSize 
                                    - E57_PAGE_CRC).astype(np.uint64)
                                    
        # set page size from segment reader
        SegmentReader.setPageSize(self.pageSize)
        
        if self.checkfile:
            # check file format
            if not (self.fileSignature=='ASTM-E57'):
                raise ValueError('No E57 file format.')
            # check file size
            if not ( (self.filePhysicalLength % self.pageSize) == 0):
                raise ValueError('File size is not compliant.')
    
    def extractXML(self):
        return SegmentReader(self.filename, 
                             self.xmlPhysicalOffset,
                             self.xmlLogicalLength).toXML()
        
    def buildRoot(self):
        import xml.etree.ElementTree as ET
        xmltxt = self.extractXML()
        #print(xmltxt)
        self.root = ET.fromstring(xmltxt) 
        
    def findElement(self, name, parent=None):
        if (parent is None):
            parent = self.root
        return parent.find('e57:'+name, E57_NS)
        
    def iterElements(self, name, parent=None):
        if (parent is None):
            parent = self.root
        return parent.iterfind('.//e57:'+name, E57_NS)      
 
    def readCompressedVectorSectionHeader(self, offset):
        return E57CompressedVectorSectionHeader(self.filename, offset)   
        
    def readDataPacketHeader(self, offset):
        return E57DataPacketHeader(self.filename, offset)   

    def readIndexPacketHeader(self, offset):
        return E57IndexPacketHeader(self.filename, offset)                       
        
    def bitsNeeded(self, maximum, minimum):
        # like the c variant ???
        state = maximum - minimum
        if ((0xFFFFFFFF00000000 & state)>0):
            return 64
        elif((0xFFFF0000 & state)>0):
            return 32
        elif((0xFF00 & state)>0):
            return 16   
        elif((0xF0 & state)>0):
            return 8       
        elif((0xC & state)>0):
            return 4   
        elif((0x2 & state)>0):
            return 2     
        elif((0x2 & state)>0):
            return 1 
        return None
        
    def extractCompressedVector(self):
        data = self.findElement('data3D')
        for pts in self.iterElements('points'):
            if (pts.attrib['type']=='CompressedVector'):
                pos = int(pts.attrib['fileOffset'])
                cnt = int(pts.attrib['recordCount'])
                
                proto = self.findElement('prototype', pts)
                cx = self.findElement('cartesianX', proto)
                
                fx = np.array([cx.attrib['minimum'], cx.attrib['maximum']],
                                dtype=np.float)
                print('minimum',cx.attrib['minimum'])
                print('maximum',cx.attrib['maximum'])
        
                  
                cv = self.readCompressedVectorSectionHeader(pos)
                dh = self.readDataPacketHeader(cv['dataPhysicalOffset'])
                
                offset = cv['dataPhysicalOffset']
                offset += dh['packetLogicalLengthMinus1']             
                idx = self.readIndexPacketHeader(offset)
        
                print(pos)
                print(cnt)
                print('sectionLogicalLength: ', cv['sectionLogicalLength'])
                print('filePhysicalLength: ',self.filePhysicalLength)
                print('dataPhysicalOffset', cv['dataPhysicalOffset'])
                print('packetLogicalLengthMinus1', 
                        dh['packetLogicalLengthMinus1'])
                print('bytestreamCount', dh['bytestreamCount'])


class SegmentReader:
    
    PageSize    = E57_STD_PAGE_SIZE
    PageContent = E57_STD_PAGE_SIZE - E57_PAGE_CRC
    
    @classmethod
    def setPageSize(cls, ps):
        cls.PageSize = ps
        cls.PageContent = cls.PageSize - E57_PAGE_CRC
    
    def __init__(self, filename, offset=0, count=1):
        self.filename  = filename
        self.offset = offset
        self.count  = count
        self.setType()
        self.setSize()
        length = self.size * count
        real_length = length
        self.position = self.offset
        
        # check position in page
        start  = (self.position  % self.PageSize)
        first  = np.array([(self.PageContent-start)],dtype=np.uint64)
        diff   = (length - first[0]).astype(np.uint64)
        if (first[0]>=length):
            pages = [length]
        else:
            pages  = np.full((diff // self.PageSize).astype(np.uint64), 
                    self.PageContent, np.uint64)
            pages = np.append(first, pages)
            modulo = (diff % self.PageSize).astype(np.uint64)
            pages = np.append(pages,  np.array((modulo).astype(np.uint64)))
            # correct the length because we lost with crc
            pages[-1] = (pages[-1] + (len(pages)-2)*E57_PAGE_CRC).astype(
                                                                    np.uint64) 
            # maybe the last page is now to big
            while (pages[-1] >= self.PageContent):
                pages = np.append(pages,(pages[-1]
                        -self.PageContent+E57_PAGE_CRC).astype(np.uint64))
                pages[-2] = self.PageContent
            # calc the real length
            real_length = length + ((len(pages)-1)*E57_PAGE_CRC)
            
        self.position += real_length
        self.position = int(self.position)
        
        # get content
        content = bytearray()
        offset = self.offset
        for page in pages:
            if (page>0):
                if E57_DEBUG:
                    print('Reading: ',page)
                    content.extend(np.fromfile(self.filename, np.byte,
                                                  count=int(page), 
                                                  offset=offset))
                    offset = np.sum([offset, 
                                     page, 
                                     E57_PAGE_CRC],
                                     dtype=np.uint64)
        
        self.result = np.frombuffer(content, dtype=self.type)
        self.validate()
                                 
    def setType(self):
        self.type =  np.dtype(np.byte)
        
    def toXML(self):
        return bytearray(self.result).decode('utf-8')

    def setSize(self):
        self.size = self.type.itemsize
        
    def isSingle(self):
        return (self.count==1)

    def __getitem__(self, key):
        if self.isSingle:
            return self.result[key][0]
        else:
            return self.result[key]
            
    def validate(self):
        return None

class E57Header(SegmentReader):

    def setType(self):
        self.type = np.dtype( [ ('fileSignature', np.dtype('S8')),
        	 				 ('majorVersion', np.uint32),
        					 ('minorVersion', np.uint32),
        					 ('filePhysicalLength', np.uint64),
        					 ('xmlPhysicalOffset', np.uint64),
        					 ('xmlLogicalLength', np.uint64),
        					 ('pageSize', np.uint64) ])


class E57CompressedVectorSectionHeader(SegmentReader):
    
    def setType(self):
        self.type = np.dtype( [ ('sectionId', np.uint8),                     
    	                    ('reserved1', np.uint8, (7,)),
    					    ('sectionLogicalLength', np.uint64),
                            ('dataPhysicalOffset', np.uint64),
                            ('indexPhysicalOffset', np.uint64) ] )
                            
    def validate(self):
        if not (self['sectionId']==E57_COMPRESSED_VECTOR_SECTION):
            raise ValueError('No compressed vector section.')
        return True     

class E57DataPacketHeader(SegmentReader):
    
    def setType(self):
        self.type = np.dtype( [ ('packetType', np.uint8),
    	                   ('packetFlags', np.uint8),
    					   ('packetLogicalLengthMinus1', np.uint16),
                           ('bytestreamCount', np.uint16) ] )
                            
    def validate(self):
        if not (self['packetType']==E57_DATA_PACKET):
            raise ValueError('No data packet.')
        return True 

class E57IndexPacketHeader(SegmentReader):
    
    def setType(self):
        self.type = np.dtype( [ ('packetType', np.uint8),
    	                  ('packetFlags', np.uint8),
    					  ('packetLogicalLengthMinus1', np.uint16),
                          ('entryCount', np.uint16),
                          ('indexLevel', np.uint8),
                          ('reserved1', np.uint8, (9,))])
                            
    def validate(self):
        if not (self['packetType']==E57_INDEX_PACKET):
            raise ValueError('No index packet.')
        return True
    
# testing   
# test data
#http://www.libe57.org/data.html  

from pathlib import Path
    
e57 = E57(str(Path.home())+'/Downloads/bunnyDouble.e57')
#e57 = E57(str(Path.home())+'/Downloads/pump.e57')
#e57 = E57(str(Path.home())+'/Downloads/garage.e57')

e57.extractCompressedVector()





