import sys
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import regex as re

class Selected():
    def __init__(self):
        self.filetype = ''
        self.filespath = []
        self.text = ''

class Browse(QWidget):

    def __init__(self):
        super().__init__()

        self.title = 'Samplesheet editor v1'
        self.left = 10
        self.top = 10
        self.width = 640
        self.height = 480
        self.selected = Selected()
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)     
        self.show()
    
    def openFileNamesDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        files, _ = QFileDialog.getOpenFileNames(self,"", "","Sample sheet files (*.ss, *.samplesheet);;Fastq files (*.fastq*);; BAM files (*.bam);; VCF files (*.vcf)", options=options)
        if files:
            for filename in files:
                if filename.endswith('ss') or filename.endswith('samplesheet'):
                    f = open(filename, 'r')
                    data = f.read()
                    self.selected.text = data
                    self.selected.filespath += [filename]
                    self.selected.filetype = 'samplesheet'
                elif filename.endswith('fastq.gz') or filename.endswith('fastq'):
                    self.selected.filespath += [filename]
                    self.selected.filetype = 'fastq'
                elif filename.endswith('bam'):
                    self.selected.filespath += [filename]
                    self.selected.filetype = 'bam'
                elif filename.endswith('vcf'):
                    self.selected.filespath += [filename]
                    self.selected.filetype = 'vcf'

    def saveFileDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self,"Save sample sheet","","All Files (*);;Text Files (*.txt)", options=options)
        if fileName:
            self.fileName = fileName

class BrowseOpen(Browse):
    def __init__(self):
        super().__init__()

    def initUI(self): 
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.openFileNamesDialog()
        self.show()

class BrowseSave(Browse):
    def __init__(self):
        self.fileName = ''
        super().__init__()
    def initUI(self):
        self.saveFileDialog()



class Samplesheet_editor(QWidget):
    def __init__(self, parent = None):
        
        super(Samplesheet_editor, self).__init__(parent)

        layout = QVBoxLayout()
        self.btn = QPushButton("Search Files...")
        self.btn.clicked.connect(self.getfile)
        layout.addWidget(self.btn)

        self.btn2 = QPushButton("Save Samplesheet")
        self.btn2.clicked.connect(self.savefile)
        layout.addWidget(self.btn2)

        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.setWindowTitle("Samplesheet editor v1.0")

        self.show()

    #table functions
    def selectedRow(self):
        if self.table.selectionModel().hasSelection():
            row =  self.table.selectionModel().selectedIndexes()[0].row()
            return int(row)

    def selectedColumn(self):
        if self.table.selectionModel().hasSelection():
            column =  self.table.selectionModel().selectedIndexes()[0].column()
            return int(column)
    
    def removeRow(self):
        if self.table.rowCount() > 0:
            row = self.selectedRow()
            table.removeRow(row)
            self.isChanged = True

    def addRow(self):
        if self.table.rowCount() > 0:
            if self.table.selectionModel().hasSelection():
                row = self.selectedRow()
                item = QTableWidgetItem("")
                self.table.insertRow(row, 0, item)
            else:
                row = 0
                item = QTableWidgetItem("")
                self.table.insertRow(row, 0, item)
                self.table.selectRow(0)    
        else:
            self.table.setRowCount(1)
        if self.table.columnCount() == 0:
            self.addColumn()
            self.table.selectRow(0)
        self.isChanged = True

    def removeColumn(self):
        self.table.removeColumn(self.selectedColumn())
        self.isChanged = True

    def addColumn(self):
        count = self.table.columnCount()
        self.table.setColumnCount(count + 1)
        self.table.resizeColumnsToContents()
        self.isChanged = True
        if self.table.rowCount() == 0:
            self.addRow()
            self.table.selectRow(0)

    def deleteRowByContext(self, event):
        row = self.selectedRow()
        self.table.removeRow(row)
        self.table.selectRow(row)
        self.isChanged = True

    def addRowByContext(self, event):
        if self.table.columnCount() == 0:
            self.table.setColumnCount(1) 
        if self.table.rowCount() == 0:
            self.table.setRowCount(1) 
            self.table.selectRow(0)
        else:
            row = self.selectedRow()
            self.table.insertRow(row + 1)
            self.table.selectRow(row + 1)
        self.isChanged = True

    def addRowByContext2(self, event):
        if self.table.columnCount() == 0:
            self.table.setColumnCount(1) 
        if self.table.rowCount() == 0:
            self.table.setRowCount(1) 
            self.table.selectRow(0)
        else:
            row = self.selectedRow() 
            self.table.insertRow(row)
            self.table.selectRow(row)
        self.isChanged = True

    def addColumnBeforeByContext(self, event):
        if self.table.columnCount() == 0:
            self.table.setColumnCount(1) 
        else:
            col = self.selectedColumn()
            self.table.insertColumn(col)
        if self.table.rowCount() == 0:
            self.table.setRowCount(1) 
        self.isChanged = True

    def addColumnAfterByContext(self, event):
        if self.table.columnCount() == 0:
            self.table.setColumnCount(1) 
        else:
            col = self.selectedColumn() + 1
            self.table.insertColumn(col)
        if self.table.rowCount() == 0:
            self.table.setRowCount(1) 
        self.isChanged = True

    def deleteColumnByContext(self, event):
        col = self.selectedColumn()
        self.table.removeColumn(col)
        self.isChanged = True


    def contextMenuEvent(self, event):
        self.menu = QMenu(self)
        if self.table.selectionModel().hasSelection():
            # delete selected Row
            deleteRowAction = QAction(QIcon.fromTheme("edit-delete"), 'delete Row', self)
            deleteRowAction.triggered.connect(lambda: self.deleteRowByContext(event))
            # add Row after
            addRowAfterAction = QAction(QIcon.fromTheme("add"), 'insert new Row after', self)
            addRowAfterAction.triggered.connect(lambda: self.addRowByContext(event))
            # add Row before
            addRowBeforeAction = QAction(QIcon.fromTheme("add"),'insert new Row before', self)
            addRowBeforeAction.triggered.connect(lambda: self.addRowByContext2(event))
            # add Column before
            addColumnBeforeAction = QAction(QIcon.fromTheme("add"),'insert new Column before', self)
            addColumnBeforeAction.triggered.connect(lambda: self.addColumnBeforeByContext(event))
            # add Column after
            addColumnAfterAction = QAction(QIcon.fromTheme("add"),'insert new Column after', self)
            addColumnAfterAction.triggered.connect(lambda: self.addColumnAfterByContext(event))
            # delete Column
            deleteColumnAction = QAction(QIcon.fromTheme("edit-delete"), 'delete Column', self)
            deleteColumnAction.triggered.connect(lambda: self.deleteColumnByContext(event))
            
            ###
            self.menu.addAction(addRowAfterAction)
            self.menu.addAction(addRowBeforeAction)
            self.menu.addSeparator()
            self.menu.addAction(addColumnBeforeAction)
            self.menu.addAction(addColumnAfterAction)
            self.menu.addSeparator()
            self.menu.addAction(deleteRowAction)
            self.menu.addAction(deleteColumnAction)
            self.menu.popup(QCursor.pos())

    def showSamplesheet(self,files_array,filetype):
        
        if filetype == 'samplesheet':

            samplesheet = [a.rstrip() for a in open(files_array[0],'r').readlines()]
            self.table.setRowCount(len(samplesheet))
            n_column = len(samplesheet[0].split('\t'))
            type = samplesheet[0].split('\t')[1]
            self.table.setColumnCount(n_column)
            for line in samplesheet:
                for item in line.split('\t'):
                    self.table.setItem(samplesheet.index(line), line.split('\t').index(item), QTableWidgetItem(item))
            if type.endswith('fast') or type.endswith('fastq.gz'):
                labels = ('Sample ID', 'FASTQ R1', 'FASTQ R2','FASTQ I1', 'FASTQ I2')
            elif type.endswith('bam'):
                labels = ('Sample ID', 'BAM')
            elif type.endswith('vcf'):
                labels = ('Sample ID', 'VCF', 'TSV LIST')
            else:
                labels = ('errore','errore')

            self.table.setHorizontalHeaderLabels(labels)

        if filetype == 'fastq':

            self.table.setRowCount(1)
            self.table.setColumnCount(3)
            row = 0
            for file in files_array:
                fastq_path = '/'.join(file.split('/')[:-1])
                fastq_name = file.split('/')[-1]
                sample_name = re.sub('-','_',fastq_name.split('_')[0])
                if '_R1_' in fastq_name:
                    row += 1
                    fastq_r1 = file
                    self.table.insertRow(row)
                    self.table.setItem(row-1, 0, QTableWidgetItem(sample_name))
                    self.table.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                    fastq_r2 = fastq_path + '/'+ re.sub('_R1_','_R2_',fastq_name)
                    fastq_i1 = fastq_path + '/'+ re.sub('_R1_','_I1_',fastq_name)
                    fastq_i2 = fastq_path + '/'+ re.sub('_R1_','_I2_',fastq_name)
                    if fastq_r2 in files_array:
                        self.table.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                    if fastq_i1 in files_array:
                        self.table.insertColumn(3)
                        self.table.insertRow(row)
                        self.table.setItem(row-1, 3, QTableWidgetItem(fastq_i1))
                    if fastq_i2 in files_array:
                        self.table.insertColumn(4)
                        self.table.setItem(row-1, 4, QTableWidgetItem(fastq_i2))
                else:
                    continue

            labels = ('Sample ID', 'FASTQ R1', 'FASTQ R2','FASTQ I1', 'FASTQ I2')

            self.table.setHorizontalHeaderLabels(labels)
            self.table.removeRow(row)

        if filetype == 'bam':

            self.table.setRowCount(1)
            self.table.setColumnCount(2)
            labels = ('Sample ID', 'BAM')
            self.table.setHorizontalHeaderLabels(labels)
            row = 0
            for file in files_array:
                bam_path = '/'.join(file.split('/')[:-1])
                bam_name = file.split('/')[-1]
                sample_name = bam_name.split('.')[0]
                row += 1
                bam = file
                self.table.insertRow(row)
                self.table.setItem(row-1, 0, QTableWidgetItem(sample_name))
                self.table.setItem(row-1, 1, QTableWidgetItem(bam))
            self.table.removeRow(row)

        if filetype == 'vcf':
            pass

        header = self.table.horizontalHeader()
        #header.setResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)    
        self.table.sortItems(0, Qt.AscendingOrder)

    def getfile(self):
        browse = BrowseOpen()
        if browse:
            self.showSamplesheet(browse.selected.filespath, browse.selected.filetype)

    def savefile(self):
        ex = BrowseSave()
        if ex:
            with open(ex.fileName,'w') as file:
                for row in range(self.table.rowCount()):
                    rowdata = []
                    for column in range(self.table.columnCount()):
                        item = self.table.item(row, column)
                        if item is not None:
                            rowdata.append(item.text())
                        else:
                            rowdata.append('')
                    file.write('\t'.join(rowdata) +'\n')
            file.close()      




