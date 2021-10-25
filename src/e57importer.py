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


class E57:

    def __init__(self, filename, checkfile=True): 
        self.filename  = filename
        self.checkfile = checkfile 
        self.readHeader()
        
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
        self.pageContent        = int(self.pageSize - E57_PAGE_CRC)
        
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
        start  = e57.xmlPhysicalOffset % self.pageSize
        first  = np.array((start-E57_PAGE_CRC).astype(np.uint64))
        diff   = (self.xmlLogicalLength - start).astype(np.uint64)
        pages  = np.full((diff // self.pageSize), self.pageContent, np.uint64)
        modulo = (diff % self.pageSize).astype(np.uint64) 
        pages = np.append(first, pages)
        if (modulo > 0):
            pages = np.append(pages,  np.array((modulo-E57_PAGE_CRC).astype(np.uint64))) 
        offset = self.xmlPhysicalOffset
        
        # get xml content
        xmltxt = bytearray()
        for page in pages:
            xmltxt.extend(np.fromfile(self.filename, np.byte, count=page, offset=offset))
            offset = np.sum([offset, page, E57_PAGE_CRC],dtype=np.uint64)
        
        return xmltxt.decode('iso-8859-5') # why only this work?, it should be utf-8
        
        
    def extractCompressedVector(self):
        import re, struct
        
        txt = self.extractXML()
        vec = re.search(r'CompressedVector(.*?)>',txt).group(1)
        pos =  int(re.search(r'fileOffset="(.*?)"',vec).group(1))
        cnt =  int(re.search(r'recordCount="(.*?)"',vec).group(1))
        
        offsetx = (pos * self.pageSize).astype(np.uint64)
        
        print(offsetx)
        print(pos)
        print(cnt)

# testing   
# test data
#http://www.libe57.org/data.html  

from pathlib import Path
    
e57 = E57(str(Path.home())+'/Downloads/bunnyDouble.e57')
txt = e57.extractXML()
print(txt)

