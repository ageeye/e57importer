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
        dtheader = np.dtype( [ ('fileSignature', np.dtype('S8')),
        	 				 ('majorVersion', np.uint32),
        					 ('minorVersion', np.uint32),
        					 ('filePhysicalLength', np.uint64),
        					 ('xmlPhysicalOffset', np.uint64),
        					 ('xmlLogicalLength', np.uint64),
        					 ('pageSize', np.uint64) ])
        header = np.fromfile(self.filename, dtheader, count=1)
        self.fileSignature      = header['fileSignature'][0].decode()
        self.majorVersion       = header['majorVersion'][0]
        self.minorVersion       = header['minorVersion'][0]
        self.filePhysicalLength = header['filePhysicalLength'][0]
        self.xmlPhysicalOffset  = header['xmlPhysicalOffset'][0]
        self.xmlLogicalLength   = header['xmlLogicalLength'][0]
        self.pageSize           = header['pageSize'][0]
        self.pageContent        = (self.pageSize 
                                    - E57_PAGE_CRC).astype(np.uint64)
        
        if self.checkfile:
            # check file format
            if not (self.fileSignature=='ASTM-E57'):
                raise ValueError('No E57 file format.')
            # check file size
            if not ( (self.filePhysicalLength % self.pageSize) == 0):
                raise ValueError('File size is not compliant.')
    
    def extractXML(self):
        # caculate the pages
        # one page include the content and crc cecksum
        start  = (self.xmlPhysicalOffset % self.pageSize)
        first  = np.array((self.pageContent-start).astype(np.uint64))
        diff   = (self.xmlLogicalLength - first).astype(np.uint64)
        pages  = np.full((diff // self.pageSize), self.pageContent, np.uint64)
        modulo = (diff % self.pageSize).astype(np.uint64) 
        pages = np.append(first, pages)
        pages = np.append(pages,  np.array((modulo).astype(np.uint64))) 
        offset = self.xmlPhysicalOffset
        pages[-1] = (pages[-1] + (len(pages)-2)*E57_PAGE_CRC).astype(np.uint64) 
        while (pages[-1] >= self.pageContent):
            pages = np.append(pages,(pages[-1]
                            -self.pageContent+E57_PAGE_CRC).astype(np.uint64))
            pages[-2] = self.pageContent
                
        # get xml content
        xmltxt = bytearray()
        for page in pages:
            xmltxt.extend(np.fromfile(self.filename, np.byte,
                                      count=page, 
                                      offset=offset))
            offset = np.sum([offset, page, E57_PAGE_CRC],dtype=np.uint64)
        
        return xmltxt.decode('utf-8')
        
        
    def buildRoot(self):
        import xml.etree.ElementTree as ET
        xmltxt = self.extractXML()
        #print(xmltxt)
        self.root = ET.fromstring(xmltxt) 
        
    def getNS(self):
        return {'e57':'http://www.astm.org/COMMIT/E57/2010-e57-v1.0'}
        
    def findElement(self, name, parent=None):
        if (parent is None):
            parent = self.root
        return parent.find('e57:'+name, self.getNS())
        
    def iterElements(self, name, parent=None):
        if (parent is None):
            parent = self.root
        return parent.iterfind('.//e57:'+name, self.getNS())      
 
    def readCompressedVectorSectionHeader(self, offset):
        dcvsh = np.dtype( [ ('sectionId', np.uint8),                     
                            # = E57_COMPRESSED_VECTOR_SECTION
    	                    ('reserved1', np.uint8, (7,)),
    					    ('sectionLogicalLength', np.uint64),
                            ('dataPhysicalOffset', np.uint64),
                            ('indexPhysicalOffset', np.uint64) ])
        result = np.fromfile(self.filename, dcvsh, count=1, offset=offset)   
        if not (result['sectionId'][0]==E57_COMPRESSED_VECTOR_SECTION):
            raise ValueError('No compressed vector section.') 
        return result   
        
    def readDataPacketHeader(self, offset):
        ddph = np.dtype( [ ('packetType', np.uint8),
    	                   ('packetFlags', np.uint8),
    					   ('packetLogicalLengthMinus1', np.uint16),
                           ('bytestreamCount', np.uint16)])
        result = np.fromfile(self.filename, ddph, count=1, offset=offset)    
        if not (result['packetType'][0]==E57_DATA_PACKET):
            raise ValueError('No data packet.')                    
        return result   
        
    def bitsNeeded(self, maximum, minimum):
        # like the c variant
        stateCountMinus1 = maximum - minimum
        # .... NOTE: Todo
        return None
        
    def extractCompressedVector(self):
        data = self.findElement('data3D')
        for pts in self.iterElements('points'):
            if (pts.attrib['type']=='CompressedVector'):
                pos = int(pts.attrib['fileOffset'])
                cnt = int(pts.attrib['recordCount'])
                
                proto = self.findElement('prototype', pts)
                cx = self.findElement('cartesianX', proto)
                
                  
                cv = self.readCompressedVectorSectionHeader(pos)
                dh = self.readDataPacketHeader(cv['dataPhysicalOffset'][0])
                
                nex = np.fromfile(self.filename, np.int8, count=1, 
                                    offset=cv['dataPhysicalOffset'][0]+
                                    dh['packetLogicalLengthMinus1'][0])[0]
                print('next:',nex)
                
                
        
                print(pos)
                print(cnt)
                print('sectionLogicalLength: ', cv['sectionLogicalLength'][0])
                print('filePhysicalLength: ',self.filePhysicalLength)
                print('dataPhysicalOffset', cv['dataPhysicalOffset'][0])
                print('packetLogicalLengthMinus1', 
                        dh['packetLogicalLengthMinus1'][0])
                print('bytestreamCount', dh['bytestreamCount'][0])

# testing   
# test data
#http://www.libe57.org/data.html  

from pathlib import Path
    
e57 = E57(str(Path.home())+'/Downloads/bunnyDouble.e57')
#e57 = E57(str(Path.home())+'/Downloads/pump.e57')
#e57 = E57(str(Path.home())+'/Downloads/garage.e57')

e57.extractCompressedVector()


