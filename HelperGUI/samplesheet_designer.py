# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/samplesheet_designer.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets
import sys
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import regex as re
import sample_organizer as so
import json


class samplesheet_designer(QWidget):
    def __init__(self, parent = None):
        
        super(samplesheet_designer, self).__init__(parent)
        self.setupUi()
        self.init_functions()
        self.init_variables()

    def setupUi(self):
        self.setObjectName("Samplesheet_designer")
        self.resize(911, 885)
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.gridLayout.setObjectName("gridLayout")

        self.label = QtWidgets.QLabel("s")
        self.label.setAutoFillBackground(True)
        self.label.setLineWidth(1)
        self.label.setScaledContents(False)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setObjectName("label")

        self.frame = QtWidgets.QFrame(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame)


        self.label_2 = QtWidgets.QLabel(self.frame)
        font = QtGui.QFont()
        font.setPointSize(21)
        self.label_2.setFont(font)
        self.label_2.setAlignment(QtCore.Qt.AlignCenter)
        self.label_2.setObjectName("label_2")
        self.verticalLayout.addWidget(self.label_2)
        self.gridLayout.addWidget(self.frame, 0, 1, 1, 3)

        self.gridLayout.addWidget(self.label, 1, 2, 1, 1)
        self.pushButton = QtWidgets.QPushButton(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy)
        self.pushButton.setObjectName("pushButton")
        self.gridLayout.addWidget(self.pushButton, 1, 1, 1, 1)

        self.pushButton_2 = QtWidgets.QPushButton(self)
        self.pushButton_2.setObjectName("pushButton_2")
        self.gridLayout.addWidget(self.pushButton_2, 2, 1, 1, 1)

        self.radioButton_3 = QtWidgets.QRadioButton(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.radioButton_3.sizePolicy().hasHeightForWidth())
        self.radioButton_3.setSizePolicy(sizePolicy)
        self.radioButton_3.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.radioButton_3.setObjectName("radioButton_3")
        self.gridLayout.addWidget(self.radioButton_3, 4, 2, 1, 1)
        self.tableWidget = QtWidgets.QTableWidget(self)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        self.gridLayout.addWidget(self.tableWidget, 6, 1, 1, 3)

        self.tableWidget.setColumnCount(4)
        labels = ('Sample ID', 'FASTQ R1', 'FASTQ R2', 'FASTQ I2')
        self.tableWidget.setHorizontalHeaderLabels(labels)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)

        self.radioButton_2 = QtWidgets.QRadioButton(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.radioButton_2.sizePolicy().hasHeightForWidth())
        self.radioButton_2.setSizePolicy(sizePolicy)
        self.radioButton_2.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.radioButton_2.setObjectName("radioButton_2")
        self.gridLayout.addWidget(self.radioButton_2, 3, 2, 1, 1)
        self.pushButton_4 = QtWidgets.QPushButton(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton_4.sizePolicy().hasHeightForWidth())
        self.pushButton_4.setSizePolicy(sizePolicy)
        self.pushButton_4.setObjectName("pushButton_4")
        self.gridLayout.addWidget(self.pushButton_4, 1, 3, 4, 1)
        self.pushButton_3 = QtWidgets.QPushButton(self)
        self.pushButton_3.setObjectName("pushButton_3")
        self.gridLayout.addWidget(self.pushButton_3, 7, 1, 1, 1)
        self.radioButton = QtWidgets.QRadioButton(self)
        self.radioButton.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.radioButton.sizePolicy().hasHeightForWidth())
        self.radioButton.setSizePolicy(sizePolicy)
        self.radioButton.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.radioButton.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.radioButton.setChecked(True)
        self.radioButton.setObjectName("radioButton")
        self.gridLayout.addWidget(self.radioButton, 2, 2, 1, 1)
        self.pushButton_5 = QtWidgets.QPushButton(self)
        self.pushButton_5.setObjectName("pushButton_5")
        self.gridLayout.addWidget(self.pushButton_5, 7, 2, 1, 2)

        self.label_3 = QtWidgets.QLabel(self)
        self.label_3.setAlignment(QtCore.Qt.AlignCenter)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 3, 1, 1, 1)

        self.comboBox = QtWidgets.QComboBox(self)
        self.comboBox.setObjectName("comboBox")
        self.gridLayout.addWidget(self.comboBox, 4, 1, 1, 1)

        #self.comboBox.addItems(['prealignment', 'alignment','preprocessing','variantcalling','postprocessing','annotation','postannotation'])
        self.comboBox.addItems(['prealignment', 'alignment','preprocessing','variantcalling'])
        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("self", "Helper - Samplesheet designer"))
        self.label.setText(_translate("self", "Samples organization"))
        self.pushButton.setText(_translate("self", "Search Files..."))
        self.pushButton_2.setText(_translate("self", "Open Sample sheet..."))
        self.radioButton_3.setText(_translate("self", "Trios"))
        self.radioButton_2.setText(_translate("self", "Case - Control"))
        self.pushButton_4.setText(_translate("self", "Organize Samples ->"))
        self.radioButton.setText(_translate("self", "Only cases"))
        self.pushButton_5.setText(_translate("self", "Save Samplesheet"))
        self.pushButton_3.setText(_translate("Form", "Cancel Samplesheet"))
        self.label_3.setText(_translate("Form", "Pipeline Step"))
        self.label_2.setText(_translate("Form", "Samplesheet Designer"))

    def init_variables(self):
        self.step = self.comboBox.currentText()
        self.samples = {}
        self.sample_list = []
        self.out_samplesheet = {}
        self.in_samplesheet = {}

    def init_functions(self):
        self.pushButton.clicked.connect(self.search_files)
        self.pushButton_2.clicked.connect(self.search_samplesheet)
        self.tableWidget.doubleClicked.connect(self.search_single_file)
        self.pushButton_4.clicked.connect(self.open_sample_organizer)
        self.pushButton_5.clicked.connect(self.save_samplesheet)
        self.comboBox.currentIndexChanged.connect(self.step_change_action)
        #self.tableWidget.cellChanged.connect(self.item_table_changed)

    def search_single_file(self,item):
        clickeditem = self.tableWidget.item(item.row(),item.column())
        file_searcher = QFileDialog.Options()
        file_searcher |= QFileDialog.DontUseNativeDialog    
        file,_ = QFileDialog.getOpenFileName(self,"Select one file","~")
        if file:
            try:
                clickeditem.setText(file)
            except:
                self.tableWidget.setItem(item.row(), item.column(), QTableWidgetItem(file))

    def search_files(self):
        file_searcher = QFileDialog.Options()
        file_searcher |= QFileDialog.DontUseNativeDialog
        if self.step == 'variantcalling' or self.step == 'preprocessing':
            files,_ = QFileDialog.getOpenFileNames(self,"Select one or more files","~","BAM .bam (*.bam)")
        else:
            files,_ = QFileDialog.getOpenFileNames(self,"Select one or more files","~","FASTQ .fastq .fq .fastq.gz fq.gz (*.fastq *.fq *.fastq.gz *.fq.gz)")

        if files:
            self.createSamplesheet_byfilesearch(files)


    def search_samplesheet(self):
        file_searcher = QFileDialog.Options()
        file_searcher |= QFileDialog.DontUseNativeDialog    
        file,_ = QFileDialog.getOpenFileName(self,"Select one samplesheet","~","SAMPLESHEET file .samplesheet .ss (*.samplesheet *.ss)")
        if file:
            self.open_existing_Samplesheet(file)

    def getOrganization(self):
        if self.radioButton.isChecked():
            org = 'only cases'
        elif self.radioButton_2.isChecked():
            org = 'case-control'
        elif self.radioButton_3.isChecked():
            org = 'trio'
        return org
    
    def switchOrganization(self):
        org = self.out_samplesheet['sample_organization']
        if org == 'only cases':
            self.radioButton.setChecked(True)
        elif org == 'case-control':
            self.radioButton_2.setChecked(True)
        elif org == 'trio':
            self.radioButton_3.setChecked(True)
            
############################ salva le modifiche della table in real-tima ma da errore: item nonetype ###########################
    # def item_table_changed(self,row, col):
    #     changeditem = self.tableWidget.item(row,col)
    #     sample_id = self.tableWidget.item(row,0).text()

    #     if sample_id != '':
    #         if self.step == 'Pre-alignment' or self.step == 'Alignment':
    #             fastq_r1 = self.tableWidget.item(row,1).text()
    #             fastq_r2 = self.tableWidget.item(row,2).text()
    #             fastq_i2 = self.tableWidget.item(row,3).text()
    #             self.samples[self.step][sample_id]={"sample_name":sample_id,"fastq_R1":fastq_r1, "fastq_R2":"", "fastq_I2": ""}

    #         if self.step == 'Pre-processing' or self.step == 'variantcalling':
    #             bam = self.tableWidget.item(row,1).text()
    #             self.samples[self.step][sample_id]={"sample_name":sample_id,"bam":fastq_r1}

    #         if self.step == 'Post-processing':
    #             gatk_vcf = self.tableWidget.item(row,1).text()
    #             freebayes_vcf = self.tableWidget.item(row,2).text()
    #             vascan_vcf = self.tableWidget.item(row,3).text()
    #             somatic_vcf = self.tableWidget.item(row,4).text()
    #             self.samples[self.step][sample_id]={"sample_name":sample_id,"gatk_vcf":"", "freebayes_vcf":"", "vascan_vcf":"", "somatic_vcf":"" }

    #         if self.step == 'Annotation' or self.step == 'Post-annotation': 
    #             merged_vcf = self.tableWidget.item(row,1).text()
    #             variants_tsv = self.tableWidget.item(row,2).text()
    #             self.samples[self.step][sample_id]={"sample_name":sample_id,"merged_vcf":merged_vcf, "variants_tsv":variants_tsv}
#####################################################################################################################################

    def step_change_action(self):
        self.step = self.comboBox.currentText()
        labels = [] 

        if self.step == 'prealignment' or self.step == 'alignment':
            self.tableWidget.setColumnCount(4)
            labels = ('Sample ID', 'FASTQ R1', 'FASTQ R2', 'FASTQ I2')

        elif self.step == 'preprocessing' or self.step == 'variantcalling':
            self.tableWidget.setColumnCount(2)
            labels = ('Sample ID', 'BAM')

        elif self.step == 'postprocessing':
            self.tableWidget.setColumnCount(5)
            labels = ('Sample ID', 'GATK VCF', 'FREEB VCF', 'VARSCAN VCF', 'SOMATIC VCF')

        elif self.step == "annotation" or self.step == 'postannotation':
            
            self.tableWidget.setColumnCount(3)
            labels = ('Sample ID', 'MERGED VCF' ,'VARIANTS TSV')

        self.visualSamples()
        self.tableWidget.setHorizontalHeaderLabels(labels)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)      
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

    def open_existing_Samplesheet(self,file):
        self.out_samplesheet = json.loads((open(file).read()).encode('utf8'))
        self.sample_list = self.out_samplesheet["sample_list"]
        self.visualSamples()
        self.switchOrganization()


    def visualSamples(self):
        #org = self.getOrganization()
        try:
            org = self.out_samplesheet['sample_organization']
        except: 
            org = "only cases"
        self.tableWidget.setRowCount(0)
        self.tableWidget.setRowCount(1)
        header = self.tableWidget.horizontalHeader()
        #header.setStretchLastSection(True)  
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents) 
        row = 0
        self.samples[self.step] = {}
        if org == "only cases":
            for sample in self.sample_list:
                
                if self.step == 'prealignment' or self.step == 'alignment':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['case']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['case']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['case']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents) 
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                elif self.step == 'preprocessing':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))

                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                elif self.step == 'variantcalling':
                    if 'variantcalling' in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet['variantcalling'].keys():
                            sample_name = self.out_samplesheet["variantcalling"][sample]['case']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples["variantcalling"][sample_name] = {"sample_name":sample_name, "bam":bam}

            self.tableWidget.removeRow(row)
                
        elif org == "case-control":

            for sample in self.sample_list:
                if self.step == 'prealignment' or self.step == 'alignment':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['case']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['case']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['case']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents) 
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                            sample_name = self.out_samplesheet[self.step][sample]['control']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['control']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['control']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['control']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents) 
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                elif self.step == 'preprocessing':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                            sample_name = self.out_samplesheet[self.step][sample]['control']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['control']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                elif self.step == 'variantcalling':
                    if 'variantcalling' in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet["variantcalling"][sample]['case']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples["variantcalling"][sample_name] = {"sample_name":sample_name, "bam":bam}

                            sample_name = self.out_samplesheet["variantcalling"][sample]['control']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['control']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            
                            self.samples["variantcalling"][sample_name] = {"sample_name":sample_name, "bam":bam}


            self.tableWidget.removeRow(row)

        elif org == "trio":
            print('trio')
            for sample in self.sample_list:
                if self.step == 'prealignment' or self.step == 'alignment':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            print(self.out_samplesheet[self.step][sample])
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['case']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['case']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['case']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents) 
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                            sample_name = self.out_samplesheet[self.step][sample]['parent1']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['parent1']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['parent1']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['parent1']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents) 
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                            sample_name = self.out_samplesheet[self.step][sample]['parent2']["sample_name"]
                            fastq_r1 = self.out_samplesheet[self.step][sample]['parent2']["fastq_R1"]
                            fastq_r2 = self.out_samplesheet[self.step][sample]['parent2']["fastq_R2"]
                            fastq_i2 = self.out_samplesheet[self.step][sample]['parent2']["fastq_I2"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(4)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))

                            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
                            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents) 
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2":fastq_i2}

                elif self.step == 'preprocessing':
                    if self.step in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet[self.step][sample]['case']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                            sample_name = self.out_samplesheet[self.step][sample]['parent1']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['parent1']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                            sample_name = self.out_samplesheet[self.step][sample]['parent2']["sample_name"]
                            bam = self.out_samplesheet[self.step][sample]['parent2']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                elif self.step == 'variantcalling':
                    if 'variantcalling' in self.out_samplesheet.keys():
                        if sample in self.out_samplesheet[self.step].keys():
                            sample_name = self.out_samplesheet["variantcalling"][sample]['case']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['case']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples["variantcalling"][sample_name] = {"sample_name":sample_name, "bam":bam}
                            sample_name = self.out_samplesheet["variantcalling"][sample]['parent1']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['parent1']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

                            sample_name = self.out_samplesheet["variantcalling"][sample]['parent2']["sample_name"]
                            bam = self.out_samplesheet["variantcalling"][sample]['parent2']["bam"]
                            row += 1
                            self.tableWidget.insertRow(row)
                            self.tableWidget.setColumnCount(2)
                            self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                            self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                            self.samples[self.step][sample_name] = {"sample_name":sample_name, "bam":bam}

            self.tableWidget.removeRow(row) 

    def checkInfileStep(self, filetype):
        step = self.comboBox.currentText()
        if filetype == 'fastq':
            if step == 'prealignment' or step == 'alignment':
                return True
            else:
                return False
        elif filetype == 'bam':
            if step == 'preprocessing' or step == 'variantcalling':
                return True
            else:
                return False


    def createSamplesheet_byfilesearch(self, files):
        self.samples[self.step] = {}
        file_list = [f.rstrip() for f in files]
       

        if file_list[0].endswith('fastq') or file_list[0].endswith('fastq.gz') or file_list[0].endswith('fq.gz') or file_list[0].endswith('fq'):
            if self.checkInfileStep('fastq'):
                self.tableWidget.setRowCount(1)
                self.tableWidget.setColumnCount(4)
                row = 0
                for file in file_list:
                    fastq_path = '/'.join(file.split('/')[:-1])
                    fastq_name = file.split('/')[-1]
                    sample_name = re.sub('-','_',re.split('_S'+r'(\d+)', fastq_name)[0])
                    #sample_name = re.sub('-','_',fastq_name.split('_')[0])
                    if '_R1_' in fastq_name:
                        row += 1
                        fastq_r1 = file
                        self.tableWidget.insertRow(row)
                        self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                        self.tableWidget.setItem(row-1, 1, QTableWidgetItem(fastq_r1))
                        fastq_r2 = fastq_path + '/'+ re.sub('_R1_','_R2_',fastq_name)
                        fastq_i2 = fastq_path + '/'+ re.sub('_R1_','_I2_',fastq_name)

                        self.samples[self.step][sample_name]= {"sample_name":sample_name,"fastq_R1":fastq_r1, "fastq_R2":"", "fastq_I2": ""}
                        if sample_name not in self.sample_list:
                            self.sample_list += [sample_name]

                        if fastq_r2 in file_list:
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(fastq_r2))
                            self.samples[self.step][sample_name]["fastq_R2"] = fastq_r2
                        else:
                            self.tableWidget.setItem(row-1, 2, QTableWidgetItem(""))
                        if fastq_i2 in file_list:
                            self.tableWidget.insertColumn(4)
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(fastq_i2))
                            self.samples[self.step][sample_name]["fastq_I2"] = fastq_i2
                        else:
                            self.tableWidget.setItem(row-1, 3, QTableWidgetItem(""))
                        #    self.samples[sample_name]["fastq_I2"] = fastq_i2
                    else:
                        continue
                labels = ('Sample ID', 'FASTQ R1', 'FASTQ R2', 'FASTQ I2')

                self.tableWidget.setHorizontalHeaderLabels(labels)
                self.tableWidget.removeRow(row)

        elif file_list[0].endswith('bam'):
            print('bam files')
            if self.checkInfileStep('bam'):
                print('bam files')
                self.tableWidget.setRowCount(1)
                self.tableWidget.setColumnCount(2)
                labels = ('Sample ID', 'BAM')
                self.tableWidget.setHorizontalHeaderLabels(labels)
                row = 0
                for file in file_list:
                    bam_path = '/'.join(file.split('/')[:-1])
                    bam_name = file.split('/')[-1]
                    sample_name = bam_name.split('.')[0]
                    row += 1
                    bam = file
                    self.tableWidget.insertRow(row)
                    self.tableWidget.setItem(row-1, 0, QTableWidgetItem(sample_name))
                    self.tableWidget.setItem(row-1, 1, QTableWidgetItem(bam))
                    self.samples[self.step][sample_name]= {"sample_name":sample_name,"bam":bam}
                    if sample_name not in self.sample_list:
                        self.sample_list += [sample_name]
                self.tableWidget.removeRow(row)

        elif file_list[0].endswith('vcf'):
            pass

        header = self.tableWidget.horizontalHeader()
        #header.setStretchLastSection(True)  
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)  
        #header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tableWidget.sortItems(0, Qt.AscendingOrder)



##### CONTEXT MENU EVENT #########################################################

    def selectedRow(self):
        if self.tableWidget.selectionModel().hasSelection():
            row =  self.tableWidget.selectionModel().selectedIndexes()[0].row()
        else:
            row = self.tableWidget.rowCount()-1
        return int(row)

    def selectedColumn(self):
        if self.tableWidget.selectionModel().hasSelection():
            column =  self.tableWidget.selectionModel().selectedIndexes()[0].column()
            return int(column)
    
    def removeRow(self):
        if self.tableWidget.rowCount() > 0:
            row = self.selectedRow()
            table.removeRow(row)
            self.isChanged = True

    def addRow(self):
        if self.tableWidget.rowCount() > 0:
            if self.tableWidget.selectionModel().hasSelection():
                row = self.selectedRow()
                self.tableWidget.insertRow(row)
            else:
                row = 0
                self.tableWidget.insertRow(row)
                self.tableWidget.selectRow(0)                  
        else:
            row = 0
            self.tableWidget.setRowCount(1)

        if self.tableWidget.columnCount() == 0:
            self.addColumn()
            self.tableWidget.selectRow(0)

        for col in range(self.tableWidget.columnCount()):
            item = QTableWidgetItem("")
            self.tableWidget.setItem(row, col, item)

        self.isChanged = True

    def removeColumn(self):
        self.tableWidget.removeColumn(self.selectedColumn())
        self.isChanged = True

    def addColumn(self):
        count = self.tableWidget.columnCount()
        self.tableWidget.setColumnCount(count + 1)
        self.tableWidget.resizeColumnsToContents()
        self.isChanged = True
        if self.tableWidget.rowCount() == 0:
            self.addRow()
            self.tableWidget.selectRow(0)

    def deleteRowByContext(self, event):
        row = self.selectedRow()
        print(self.sample_list)        
        self.sample_list.remove(self.tableWidget.item(row,0).text())
        self.tableWidget.removeRow(row)
        self.tableWidget.selectRow(row)
        self.isChanged = True
        print(self.sample_list) 


    def addRowByContext(self, event):
        if self.tableWidget.columnCount() == 0:
            self.tableWidget.setColumnCount(1) 
        if self.tableWidget.rowCount() == 0:
            row = 0
            self.tableWidget.setRowCount(1) 
            self.tableWidget.selectRow(0)
        else:
            row = self.selectedRow()
            self.tableWidget.insertRow(row + 1)
            self.tableWidget.selectRow(row + 1)
        self.isChanged = True
        for col in range(self.tableWidget.columnCount()):
            item = QTableWidgetItem("")
            self.tableWidget.setItem(row, col, item)

    def addRowByContext2(self, event):
        if self.tableWidget.columnCount() == 0:
            self.tableWidget.setColumnCount(1) 
        if self.tableWidget.rowCount() == 0:
            row = 0
            self.tableWidget.setRowCount(1) 
            self.tableWidget.selectRow(0)
        else:
            row = self.selectedRow() 
            self.tableWidget.insertRow(row)
            self.tableWidget.selectRow(row)
        self.isChanged = True
        for col in range(self.tableWidget.columnCount()):
            item = QTableWidgetItem("")
            self.tableWidget.setItem(row, col, item)

    def addColumnBeforeByContext(self, event):
        if self.tableWidget.columnCount() == 0:
            self.tableWidget.setColumnCount(1) 
        else:
            col = self.selectedColumn()
            self.tableWidget.insertColumn(col)
        if self.tableWidget.rowCount() == 0:
            self.tableWidget.setRowCount(1) 
        self.isChanged = True

    def addColumnAfterByContext(self, event):
        if self.tableWidget.columnCount() == 0:
            self.tableWidget.setColumnCount(1) 
        else:
            col = self.selectedColumn() + 1
            self.tableWidget.insertColumn(col)
        if self.tableWidget.rowCount() == 0:
            self.tableWidget.setRowCount(1) 
        self.isChanged = True

    def deleteColumnByContext(self, event):
        col = self.selectedColumn()
        self.tableWidget.removeColumn(col)
        self.isChanged = True


    def contextMenuEvent(self, event):
        if self.tableWidget.selectionModel().hasSelection():
            self.menu = QMenu(self)
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
            #self.menu.addAction(addColumnBeforeAction)
            #self.menu.addAction(addColumnAfterAction)
            #self.menu.addSeparator()
            self.menu.addAction(deleteRowAction)
            #self.menu.addAction(deleteColumnAction)
            self.menu.popup(QCursor.pos())

        else:
            self.menu = QMenu(self)
            addRowAction= QAction(QIcon.fromTheme("add"), 'insert new Row', self)
            addRowAction.triggered.connect(lambda: self.addRowByContext(event))
            
            self.menu.addAction(addRowAction)
            self.menu.popup(QCursor.pos())
###################################################################################
    

    def open_sample_organizer(self):
        
        #self.info_from_table()
        org = self.getOrganization()
        if len(self.sample_list)>0:
            self.sample_organizer = so.sample_organizer()
            self.sample_organizer.set_Sample_organizer(org, self.sample_list, self.samples)
            self.sample_organizer.show()
            self.sample_organizer.Accept_pushButton.clicked.connect(self.saveorganization)
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Warning")
            msg.setText("Add some samples")
            msg.setIcon(msg.Warning)
            msg.setStandardButtons(QMessageBox.Ok)
            x = msg.exec_()

    def saveorganization(self):
        pipeline_step = self.comboBox.currentText()
        self.out_samplesheet = self.sample_organizer.sample_organization

    def save_samplesheet(self):
        pipeline_step = self.comboBox.currentText()
        print(self.out_samplesheet)
        try:
            self.out_samplesheet["sample_list"] = self.sample_organizer.sample_list
            #self.out_samplesheet = self.sample_organizer.sample_organization
        except:
            self.out_samplesheet["sample_list"] = self.sample_list

        try:
            self.out_samplesheet["sample_organization"] = self.getOrganization()
        except:
            self.out_samplesheet["sample_organization"] = "only cases"

        self.info_from_table()
        fileName,_ = QFileDialog.getSaveFileName(self, 'Dialog Title', '', "Samplesheet file ( *.ss *.samplesheet)")
        if fileName:
            with open(fileName, 'w') as ss:
                json.dump(self.out_samplesheet, ss, indent=4)

    def info_from_table(self):

        rows = self.tableWidget.rowCount()
        self.samples[self.step] = {}
        self.sample_list = []

        for row in range(rows):
            sample_id = self.tableWidget.item(row,0).text()
            if sample_id != "": self.sample_list += [sample_id]
            if self.step == 'prealignment':
                fastq_r1 = self.tableWidget.item(row,1).text()
                fastq_r2 = self.tableWidget.item(row,2).text()
                fastq_i2 = self.tableWidget.item(row,3).text()
                self.samples["prealignment"][sample_id]={"sample_name":sample_id,"fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2": fastq_i2}
            
            if self.step == 'alignment':
                fastq_r1 = self.tableWidget.item(row,1).text()
                fastq_r2 = self.tableWidget.item(row,2).text()
                fastq_i2 = self.tableWidget.item(row,3).text()
                self.samples["alignment"][sample_id]={"sample_name":sample_id,"fastq_R1":fastq_r1, "fastq_R2":fastq_r2, "fastq_I2": fastq_i2}


            if self.step == 'preprocessing':
                bam = self.tableWidget.item(row,1).text()
                self.samples["preprocessing"][sample_id]={"sample_name":sample_id,"bam":bam}
            
            if self.step == 'variantcalling':
                bam = self.tableWidget.item(row,1).text()
                self.samples["variantcalling"][sample_id]={"sample_name":sample_id,"bam":bam}

            if self.step == 'postprocessing':
                gatk_vcf = self.tableWidget.item(row,1).text()
                freebayes_vcf = self.tableWidget.item(row,2).text()
                vascan_vcf = self.tableWidget.item(row,3).text()
                somatic_vcf = self.tableWidget.item(row,4).text()
                self.samples["postprocessing"][sample_id]={"sample_name":sample_id,"gatk_vcf":gatk_vcf, "freebayes_vcf":freebayes_vcf, "vascan_vcf":vascan_vcf, "somatic_vcf":somatic_vcf }

            if self.step == 'annotation': 
                merged_vcf = self.tableWidget.item(row,1).text()
                variants_tsv = self.tableWidget.item(row,2).text()
                self.samples["annotation"][sample_id]={"sample_name":sample_id,"merged_vcf":merged_vcf, "variants_tsv":variants_tsv}
            
            if self.step == 'postannotation': 
                merged_vcf = self.tableWidget.item(row,1).text()
                variants_tsv = self.tableWidget.item(row,2).text()
                self.samples["postannotation"][sample_id]={"sample_name":sample_id,"merged_vcf":merged_vcf, "variants_tsv":variants_tsv}
