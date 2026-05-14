# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/tool_settings.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets
import os.path
import subprocess
import json
import add_tool as at
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

class Browse(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.show()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)     
        self.show()


class tool_settings(QtWidgets.QWidget):

    def __init__(self, parent = None):
        super(tool_settings, self).__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("tool_settings")
        self.resize(1177, 890)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.frame = QtWidgets.QFrame(self)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.frame)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter_2 = QtWidgets.QSplitter(self.frame)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName("splitter_2")
        self.splitter = QtWidgets.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.tool_groupBox = QtWidgets.QGroupBox(self.splitter)
        self.tool_groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.tool_groupBox.setObjectName("tool_groupBox")
        self.gridLayout_5 = QtWidgets.QGridLayout(self.tool_groupBox)
        self.gridLayout_5.setObjectName("gridLayout_5")
        self.deleteTool_pushButton = QtWidgets.QPushButton(self.tool_groupBox)
        self.deleteTool_pushButton.setObjectName("deleteTool_pushButton")
        self.gridLayout_5.addWidget(self.deleteTool_pushButton, 0, 3, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_5.addItem(spacerItem, 0, 0, 1, 1)
        self.tool_listWidget = QtWidgets.QListWidget(self.tool_groupBox)
        self.tool_listWidget.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.tool_listWidget.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.tool_listWidget.setMidLineWidth(1)
        self.tool_listWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.tool_listWidget.setObjectName("tool_listWidget")
        self.gridLayout_5.addWidget(self.tool_listWidget, 2, 0, 1, 4)
        self.addtool_pushButton = QtWidgets.QPushButton(self.tool_groupBox)
        self.addtool_pushButton.setObjectName("addtool_pushButton")
        self.gridLayout_5.addWidget(self.addtool_pushButton, 0, 2, 1, 1)

        self.modtool_pushButton = QtWidgets.QPushButton(self.tool_groupBox)
        self.modtool_pushButton.setObjectName("addtool_pushButton")
        self.gridLayout_5.addWidget(self.modtool_pushButton, 0, 1, 1, 1)


        self.DB_groupBox = QtWidgets.QGroupBox(self.splitter)
        self.DB_groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.DB_groupBox.setObjectName("DB_groupBox")
        self.gridLayout = QtWidgets.QGridLayout(self.DB_groupBox)
        self.gridLayout.setObjectName("gridLayout")
        self.deleteDB_pushButton = QtWidgets.QPushButton(self.DB_groupBox)
        self.deleteDB_pushButton.setObjectName("deleteDB_pushButton")
        self.gridLayout.addWidget(self.deleteDB_pushButton, 0, 3, 1, 1)
        self.addDB_pushButton = QtWidgets.QPushButton(self.DB_groupBox)
        self.addDB_pushButton.setObjectName("addDB_pushButton")
        self.gridLayout.addWidget(self.addDB_pushButton, 0, 2, 1, 1)
        self.modDB_pushButton = QtWidgets.QPushButton(self.DB_groupBox)
        self.modDB_pushButton.setObjectName("addDB_pushButton")
        self.gridLayout.addWidget(self.modDB_pushButton, 0, 1, 1, 1)

        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 0, 0, 1, 1)
        self.DB_listWidget = QtWidgets.QListWidget(self.DB_groupBox)
        self.DB_listWidget.setObjectName("DB_listWidget")
        self.gridLayout.addWidget(self.DB_listWidget, 1, 0, 1, 4)
        self.ref_groupBox = QtWidgets.QGroupBox(self.splitter)
        self.ref_groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.ref_groupBox.setObjectName("ref_groupBox")
        self.gridLayout_4 = QtWidgets.QGridLayout(self.ref_groupBox)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.deleteRef_pushButton = QtWidgets.QPushButton(self.ref_groupBox)
        self.deleteRef_pushButton.setObjectName("deleteRef_pushButton")
        self.gridLayout_4.addWidget(self.deleteRef_pushButton, 0, 3, 1, 1)
        spacerItem2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_4.addItem(spacerItem2, 0, 0, 1, 1)
        self.addRef_pushButton = QtWidgets.QPushButton(self.ref_groupBox)
        self.addRef_pushButton.setObjectName("addRef_pushButton")
        self.gridLayout_4.addWidget(self.addRef_pushButton, 0, 2, 1, 1)

        self.modRef_pushButton = QtWidgets.QPushButton(self.ref_groupBox)
        self.modRef_pushButton.setObjectName("addRef_pushButton")
        self.gridLayout_4.addWidget(self.modRef_pushButton, 0, 1, 1, 1)
        
        self.ref_listWidget = QtWidgets.QListWidget(self.ref_groupBox)
        self.ref_listWidget.setObjectName("ref_listWidget")
        self.gridLayout_4.addWidget(self.ref_listWidget, 1, 0, 1, 4)
        self.groupBox_2 = QtWidgets.QGroupBox(self.splitter_2)
        self.groupBox_2.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_2.setFlat(False)
        self.groupBox_2.setCheckable(False)
        self.groupBox_2.setObjectName("groupBox_2")
        self.gridLayout_6 = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout_6.setObjectName("gridLayout_6")
        self.tableWidget = QtWidgets.QTableWidget(self.groupBox_2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tableWidget.sizePolicy().hasHeightForWidth())      
        self.tableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tableWidget.setSizePolicy(sizePolicy)
        self.tableWidget.setObjectName("tableWidget")
        self.gridLayout_6.addWidget(self.tableWidget, 2, 0, 1, 3)
        self.saveSetting_pushButton = QtWidgets.QPushButton(self.groupBox_2)
        self.saveSetting_pushButton.setObjectName("saveSetting_pushButton")
        self.gridLayout_6.addWidget(self.saveSetting_pushButton, 1, 2, 1, 1)
        self.addSetting_pushButton = QtWidgets.QPushButton(self.groupBox_2)
        self.addSetting_pushButton.setObjectName("addSetting_pushButton")
        self.gridLayout_6.addWidget(self.addSetting_pushButton, 1, 1, 1, 1)
        self.addSetting_pushButton.setEnabled(False)
        spacerItem3 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout_6.addItem(spacerItem3, 1, 0, 1, 1)
        self.gridLayout_2.addWidget(self.splitter_2, 1, 0, 1, 1)
        self.label = QtWidgets.QLabel(self.frame)
        font = QtGui.QFont()
        #font.setFamily("DejaVu Serif Condensed")
        font.setPointSize(30)
        self.label.setFont(font)
        self.label.setTextFormat(QtCore.Qt.AutoText)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setObjectName("label")
        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)
        self.verticalLayout_2.addWidget(self.frame)

        self.init_table()
        self.tableWidget.customContextMenuRequested.connect(self.show_Info_Menu)
        #self.tableWidget.clicked.connect(self.onLeftClick)

        self.retranslateUi(self)
        QtCore.QMetaObject.connectSlotsByName(self)

        self.clicked = ''
        self.configs_folder = '/'.join(os.path.dirname(os.path.realpath(__file__)).split('/')[:-1] + ['configs'])
        self.config = json.loads((open(self.configs_folder+ '/tools_cfg/tools.cfg').read()).encode('utf8'))

        self.tool_listWidget.itemClicked.connect(self.show_tool_info)
        self.DB_listWidget.itemClicked.connect(self.show_DB_info)
        self.ref_listWidget.itemClicked.connect(self.show_ref_info)

        self.addtool_pushButton.clicked.connect(self.init_add_tool)
        self.deleteTool_pushButton.clicked.connect(self.delete_tool)
        self.modtool_pushButton.clicked.connect(self.set_tool)

        self.addDB_pushButton.clicked.connect(self.init_add_DB)
        self.deleteDB_pushButton.clicked.connect(self.delete_DB)
        self.modDB_pushButton.clicked.connect(self.set_DB)

        self.addRef_pushButton.clicked.connect(self.init_add_Ref)
        self.deleteRef_pushButton.clicked.connect(self.delete_Ref)
        self.modRef_pushButton.clicked.connect(self.set_Ref)

        self.addSetting_pushButton.clicked.connect(self.init_add_new_info)

        self.saveSetting_pushButton.clicked.connect(self.save_settings)

        self.populate_lists()


    def init_table(self):
        self.tableWidget.setColumnCount(1)
        item = QtWidgets.QTableWidgetItem()
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        self.tableWidget.setHorizontalHeaderItem(0, item)     
        item = self.tableWidget.horizontalHeaderItem(0)
        item.setText(QtCore.QCoreApplication.translate("tool_settings", "Settings"))
        __sortingEnabled = self.tableWidget.isSortingEnabled()
        self.tableWidget.setSortingEnabled(False)
        self.tableWidget.setSortingEnabled(__sortingEnabled)
        self.tableWidget.setContextMenuPolicy(Qt.CustomContextMenu)        

    def populate_lists(self):

        tools_list = self.config["tools"]["list"]
        self.tool_listWidget.addItems(tools_list)

        databases_list = self.config["databases"]["list"]
        self.DB_listWidget.addItems(databases_list)

        ref_list = self.config["refGenomes_list"]
        self.ref_listWidget.addItems(ref_list) 

    def retranslateUi(self, tool_settings):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("tool_settings", "Tools Settings"))
        self.tool_groupBox.setTitle(_translate("tool_settings", "Tools"))
        self.deleteTool_pushButton.setText(_translate("tool_settings", "Delete"))
        self.addtool_pushButton.setText(_translate("tool_settings", "Add"))
        self.modtool_pushButton.setText(_translate("tool_settings", "Set"))
        self.DB_groupBox.setTitle(_translate("tool_settings", "Databases"))
        self.deleteDB_pushButton.setText(_translate("tool_settings", "Delete"))
        self.addDB_pushButton.setText(_translate("tool_settings", "Add"))
        self.modDB_pushButton.setText(_translate("tool_settings", "Set"))
        self.ref_groupBox.setTitle(_translate("tool_settings", "Reference genomes"))
        self.deleteRef_pushButton.setText(_translate("tool_settings", "Delete"))
        self.addRef_pushButton.setText(_translate("tool_settings", "Add"))
        self.modRef_pushButton.setText(_translate("tool_settings", "Set"))
        self.groupBox_2.setTitle(_translate("tool_settings", " "))
        self.saveSetting_pushButton.setText(_translate("tool_settings", "Save settings"))
        self.label.setText(_translate("tool_settings", "Tools Settings"))
        self.addSetting_pushButton.setText(_translate("tool_settings", "Add info"))

   
    def show_tool_info(self):
        self.addSetting_pushButton.setEnabled(True)
        self.tableWidget.clear()
        self.tableWidget.setColumnCount(1)
        self.tableWidget.setRowCount(0)
        self.init_table()

        item = self.tool_listWidget.currentItem()
        item_text = item.text()
        info = self.config[item_text]

        self.clicked = item_text
              
        for key in info.keys():
            n_row = self.tableWidget.rowCount()
            self.tableWidget.setRowCount(n_row+1)
            new_row = QtWidgets.QTableWidgetItem(key)
            self.tableWidget.setVerticalHeaderItem (n_row, new_row)
          
            new_item = QtWidgets.QTableWidgetItem(info[key])
            self.tableWidget.setItem(n_row, 0, new_item)
            
            
    def show_DB_info(self):
        self.addSetting_pushButton.setEnabled(True)
        self.tableWidget.clear()
        self.tableWidget.setColumnCount(1)
        self.tableWidget.setRowCount(0)
        self.init_table()

        item = self.DB_listWidget.currentItem()
        item_text = item.text()
        info = self.config[item_text]

        self.clicked = item_text
     
        for key in info.keys():
            n_row = self.tableWidget.rowCount()
            self.tableWidget.setRowCount(n_row+1)
            new_row = QtWidgets.QTableWidgetItem(key)
            self.tableWidget.setVerticalHeaderItem (n_row, new_row)         
            new_item = QtWidgets.QTableWidgetItem(info[key])
            self.tableWidget.setItem(n_row, 0, new_item)

    def show_ref_info(self):
        self.addSetting_pushButton.setEnabled(True)
        self.tableWidget.clear()
        self.tableWidget.setColumnCount(1)
        self.tableWidget.setRowCount(0)
        self.init_table()

        item = self.ref_listWidget.currentItem()
        item_text = item.text()
        info = self.config[item_text]

        self.clicked = item_text
     
        for key in info.keys():
            n_row = self.tableWidget.rowCount()
            self.tableWidget.setRowCount(n_row+1)
            new_row = QtWidgets.QTableWidgetItem(key)
            self.tableWidget.setVerticalHeaderItem (n_row, new_row)          
            new_item = QtWidgets.QTableWidgetItem(info[key])
            self.tableWidget.setItem(n_row, 0, new_item)


## TOOLS

    def set_tool(self):
        item = self.tool_listWidget.currentItem()
        if item:
            item_text = item.text()
            path = self.config[item_text]['path']
            version = self.config[item_text]['version']
            tags = self.config[item_text]['tags']
            self.init_add_tool()
            self.addTool.Save_pushButton.clicked.disconnect() 
            self.addTool.Save_pushButton.clicked.connect(self.retrieve_tool_infos)
            self.addTool.setWindowTitle("Change tool settings")
            self.addTool.path_lineEdit.setText(path)
            self.addTool.version_lineEdit.setText(version)
            self.addTool.tags_lineEdit.setText(tags)
            self.addTool.toolname_lineEdit.setText(item_text)

    def init_add_tool(self):
        self.addTool = at.Add_tool()
        self.addTool.show()
        self.addTool.Save_pushButton.clicked.connect(self.retrieve_new_tool_infos)
        self.addTool.Cancel_pushButton.clicked.connect(self.addTool_close)
        self.addTool.addTags_pushButton.clicked.connect(self.init_add_tags)
        self.addTool.pathSearch_toolButton.clicked.connect(self.tool_path_search)

    def delete_tool(self):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Delete tool")
        msg.setText("Do you want to delete this tool?")
        msg.setIcon(msg.Question)  
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:
            tools_to_delete = self.tool_listWidget.selectedItems()
            for tool in tools_to_delete:
                self.config["tools"]["list"].remove(tool.text())
                self.config.pop(tool.text())
                self.tool_listWidget.takeItem(self.tool_listWidget.row(tool))
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)

    def addTool_close(self):
        self.addTool.close()

    def retrieve_new_tool_infos(self):
        if self.addTool.toolname_lineEdit.text() != "":
            if self.addTool.toolname_lineEdit.text() in self.config["tools"]["list"]:
                msg = QtWidgets.QMessageBox()
                msg.setWindowTitle("Tool Name Error")
                msg.setText("A tool with the same name already exists!\n")
                msg.setIcon(msg.Warning)
                x = msg.exec_()
            else:
                print('funzionaa')
                self.config["tools"]["list"] += [self.addTool.toolname_lineEdit.text()]
                self.config[self.addTool.toolname_lineEdit.text()] = { 
                    "path":self.addTool.path_lineEdit.text(), 
                    "version":self.addTool.version_lineEdit.text(),
                    "tags":self.addTool.tags_lineEdit.text()}
                self.addTool.close()
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)

                self.tool_listWidget.addItem(self.addTool.toolname_lineEdit.text())
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Tool Name Error")
            msg.setText("Every tool needs a name!\nSet the tool name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()

    def retrieve_tool_infos(self):
        if self.addTool.toolname_lineEdit.text() != "":
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Save changes")
            msg.setText("Do you want to save changes?\n")
            msg.setIcon(msg.Warning)
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
            x = msg.exec_()
            if x == QMessageBox.Ok:
                old_tool = self.tool_listWidget.currentItem().text()
                new_tool = self.addTool.toolname_lineEdit.text()
                #print(self.config["tools_list"])
                index = self.config["tools"]["list"].index(old_tool)
                self.config["tools"]["list"][index] = new_tool
                del self.config[old_tool]
                
                self.config[new_tool] = { 
                    "path":self.addTool.path_lineEdit.text(), 
                    "version":self.addTool.version_lineEdit.text(),
                    "tags":self.addTool.tags_lineEdit.text()}
                self.addTool.close()
                
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)
                self.tool_listWidget.currentItem().setText(new_tool)
                #elf.tool_listWidget.addItem(new_tool)
                #print(self.config["tools_list"])
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Tool Name Error")
            msg.setText("Every tool needs a name!\nSet the tool name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()

## TAGS

    def init_add_tags(self):
            self.addTags = at.Add_tags()
            self.addTags.show()
            #self.addTags.Save_pushButton.clicked.connect(self.retrieve_tags)
            self.addTags.buttonBox.accepted.connect(self.retrieve_tags)
            self.addTags.buttonBox.rejected.connect(self.addTags_close)
            #elf.addTags.buttonBox.clicked.connect(self.addTags_close)
             
    def addTags_close(self):
        self.addTags.close()

    def retrieve_tags(self):

            tags = []

            if self.addTags.item_adapt.checkState(0) == 2: tags += ["trim_adapters"]
            if self.addTags.item_len_filt.checkState(0) == 2: tags += ["filter_fastq"]
            if self.addTags.item_q_filt.checkState(0) == 2: tags += ["filter_fastq"]
            if self.addTags.item_fq_qc.checkState(0) == 2: tags += ["fastq_QC"]
            if self.addTags.item_umi.checkState(0) == 2: tags += ["merge_UMI"]
            if self.addTags.item_alig.checkState(0) == 2: tags += ["fastq_alignment"]
            if self.addTags.item_sambam.checkState(0) == 2: tags += ["sam_to_bam"]
            if self.addTags.item_sort.checkState(0) == 2: tags += ["sortSam"]
            if self.addTags.item_bam_qc.checkState(0) == 2: tags += ["bam_QC"]
            if self.addTags.item_bam_filt.checkState(0) == 2: tags += ["filter_bam"]
            if self.addTags.item_rgroup.checkState(0) == 2: tags += ["add_readgroups"]
            if self.addTags.item_dup.checkState(0) == 2: tags += ["mark_pcr_dup"]
            if self.addTags.item_realig.checkState(0) == 2: tags += ["indel_realignment"]
            if self.addTags.item_bqsr.checkState(0) == 2: tags += ["BQ_recalibration"]
            if self.addTags.item_shortv_call.checkState(0) == 2: tags += ["variantcalling"]
            if self.addTags.item_cnv_call.checkState(0) == 2: tags += ["cnvcalling"]
            if self.addTags.item_vcf_norm.checkState(0) == 2: tags += ["vcf_norm"]
            if self.addTags.item_vcf_filt.checkState(0) == 2: tags += ["vcf_filter"]
            if self.addTags.item_vcf_to_tsv.checkState(0) == 2: tags += ["vcf_to_tsv"]
            if self.addTags.item_shortv_ann.checkState(0) == 2: tags += ["variant_ann"]
            if self.addTags.item_cnv_ann.checkState(0) == 2: tags += ["cnv_ann"]
            if self.addTags.item_filt_ann.checkState(0) == 2: tags += ["ann_filter"]
            if self.addTags.item_trs_filt_ann.checkState(0) == 2: tags += ["trs_filter"]
            if self.addTags.item_vcf_ann_to_tsv.checkState(0) == 2: tags += ["ann_vcf_to_tsv"]

            self.tagList = tags
            self.addTool.tags_lineEdit.setText(','.join(self.tagList))
            self.addTags.close()

    def populate_tags(self):

        item = self.tool_listWidget.currentItem()
        item_text = item.text()
        tags = self.config[item_text]['tags']

        self.addTags.setChecked(True)

        if 'trim_adapters' in tags: self.addTags.adap_trim_checkBox.setChecked(True)
        if 'fastq_filter' in tags: self.addTags.fastq_filter_checkBox.setChecked(True)
        if 'fastq_qc' in tags: self.addTags.fastq_QC_checkBox.setChecked(True)
        
        if 'fastq_alignment' in tags: self.addTags.fastq_align_checkBox.setChecked(True)
        if 'sam_to_bam' in tags: self.addTags.samtobam_checkBox.setChecked(True)
        if 'bam_sort' in tags: self.addTags.bam_sort_checkBox.setChecked(True)
        if 'bam_index' in tags: self.addTags.bam_index_checkBox.setChecked(True)
        if 'bam_qc' in tags: self.addTags.bam_QC_checkBox.setChecked(True)

        if 'UMI_merge' in tags: self.addTags.UMI_merge_checkBox.setChecked(True)
        if 'bam_filter' in tags: self.addTags.bam_filter_checkBox.setChecked(True)
        if 'bam_manipulate' in tags: self.addTags.readgroups_checkBox.setChecked(True)
        if 'dup_mark' in tags: self.addTags.mark_dup_checkBox.setChecked(True)
        if 'indel_realign' in tags: self.addTags.indel_real_checkBox.setChecked(True)
        if 'bqsr' in tags: self.addTags.BQSR_checkBox.setChecked(True)

        if 'variant_calling_germline' in tags: self.addTags.VC_germline_checkBox.setChecked(True)
        if 'variant_calling_som_case' in tags: self.addTags.VC_som_C_checkBox.setChecked(True)
        if 'variant_calling_som_case_control' in tags: self.addTags.VC_som_CC_checkBox.setChecked(True)
        if 'vcf_qc' in tags: self.addTags.VCF_QC_checkBox.setChecked(True)

        if 'cnv_calling' in tags: self.addTags.CNV_call_checkBox.setChecked(True)
        if 'cnv_vcf_qc' in tags: self.addTags.CNV_VCF_QC_checkBox.setChecked(True)

        if 'vcf_filter' in tags: self.addTags.VCF_filter_checkBox.setChecked(True)
        if 'vcf_merge' in tags: self.addTags.VCF_merge_checkBox.setChecked(True)
        if 'vcf_norm' in tags: self.addTags.VCF_norm_checkBox.setChecked(True)
        if 'vcf_to_tsv' in tags: self.addTags.VCFtoTSV_checkBox.setChecked(True)

        if 'annotation' in tags: self.addTags.var_ann_checkBox.setChecked(True)
        if 'cnv_annotation' in tags: self.addTags.CNV_ann_checkBox.setChecked(True)

    
## DATABASES

    def init_add_DB(self):
        self.addDB = at.Add_DB()
        self.addDB.show()
        self.addDB.Save_pushButton.clicked.connect(self.retrieve_new_db_infos)
        self.addDB.Cancel_pushButton.clicked.connect(self.addDB_close)
        self.addDB.pathSearch_toolButton.clicked.connect(self.DB_path_search)

    def delete_DB(self):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Delete DB")
        msg.setText("Do you want to delete this Database?")
        msg.setIcon(msg.Question)  
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:
            DB_to_delete = self.DB_listWidget.selectedItems()
            for db in DB_to_delete:
                self.config["databases_list"].remove(db.text())
                self.config.pop(db.text())
                self.DB_listWidget.takeItem(self.DB_listWidget.row(db))
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)

    def set_DB(self):
        item = self.DB_listWidget.currentItem()
        if item:
            item_text = item.text()
            path = self.config[item_text]['path']
            version = self.config[item_text]['version']
            tags = self.config[item_text]['tags']
            self.init_add_DB()
            self.addDB.Save_pushButton.clicked.disconnect() 
            self.addDB.Save_pushButton.clicked.connect(self.retrieve_db_infos)
            self.addDB.setWindowTitle("Change tool settings")
            self.addDB.path_lineEdit.setText(path)
            self.addDB.version_lineEdit.setText(version)
            self.addDB.DBname_lineEdit.setText(item_text)

    def addDB_close(self):
        self.addDB.close()

    def retrieve_new_db_infos(self):
        if self.addDB.DBname_lineEdit.text() != "":
            if self.addDB.DBname_lineEdit.text() in self.config["databases"]["list"]:
                msg = QtWidgets.QMessageBox()
                msg.setWindowTitle("DB Name Error")
                msg.setText("A DataBase with the same name already exists!")
                msg.setIcon(msg.Warning)
                x = msg.exec_()
            else:
                self.config["databases"]["list"] += [self.addDB.DBname_lineEdit.text()]
                self.config[self.addDB.DBname_lineEdit.text()] = { 
                    "path":self.addDB.path_lineEdit.text(), 
                    "version":self.addDB.version_lineEdit.text(),
                    "tags":"database"}
                self.addDB.close()
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)
                self.DB_listWidget.addItem(self.addDB.DBname_lineEdit.text())
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("DB Name Error")
            msg.setText("Every Database needs a name!\nSet the DB name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()

    def retrieve_db_infos(self):
        if self.addDB.DBname_lineEdit.text() != "":
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Save changes")
            msg.setText("Do you want to save changes?\n")
            msg.setIcon(msg.Warning)
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
            x = msg.exec_()
            if x == QMessageBox.Ok:
                old_db = self.DB_listWidget.currentItem().text()
                new_db = self.addDB.DBname_lineEdit.text()
                #print(self.config["tools_list"])
                index = self.config["databases"]["list"].index(old_db)
                self.config["databases"]["list"][index] = new_db
                del self.config[old_db]
                
                self.config[new_db] = { 
                    "path":self.addDB.path_lineEdit.text(), 
                    "version":self.addDB.version_lineEdit.text(),
                    "tags":"database"}
                self.addDB.close()
                
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)
                self.DB_listWidget.currentItem().setText(new_db)
                #elf.tool_listWidget.addItem(new_tool)
                #print(self.config["tools_list"])
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("DB Name Error")
            msg.setText("Every Database needs a name!\nSet the DB name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()

## REFERENCE

    
    def init_add_Ref(self):
        self.addRef = at.Add_Ref()
        self.addRef.show()
        self.addRef.Save_pushButton.clicked.connect(self.retrieve_new_ref_infos)
        self.addRef.Cancel_pushButton.clicked.connect(self.addRef_close)
        self.addRef.pathSearch_toolButton.clicked.connect(self.Ref_path_search)

    def delete_Ref(self):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Delete Reference")
        msg.setText("Do you want to delete this Reference?")
        msg.setIcon(msg.Question)  
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:
            ref_to_delete = self.ref_listWidget.selectedItems()
            for ref in ref_to_delete:
                self.config["refGenomes_list"].remove(ref.text())
                self.config.pop(ref.text())
                self.ref_listWidget.takeItem(self.ref_listWidget.row(ref))
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)

    def set_Ref(self):
        item = self.ref_listWidget.currentItem()
        if item:
            ref_text = item.text()
            fasta = self.config[ref_text]['fasta']
            version = self.config[ref_text]['version']
            tags = self.config[ref_text]['tags']
            self.init_add_Ref()
            self.addRef.Save_pushButton.clicked.disconnect() 
            self.addRef.Save_pushButton.clicked.connect(self.retrieve_ref_infos)
            self.addRef.setWindowTitle("Change ref settings")
            self.addRef.path_lineEdit.setText(fasta)
            self.addRef.ref_dict = self.config[ref_text]['dict']
            self.addRef.version_lineEdit.setText(version)
            self.addRef.Refname_lineEdit.setText(ref_text)

    def addRef_close(self):
        self.addRef.close()

    def retrieve_new_ref_infos(self):
        if self.addRef.Refname_lineEdit.text() != "":
            if self.addRef.Refname_lineEdit.text() in self.config["refGenomes_list"]:
                msg = QtWidgets.QMessageBox()
                msg.setWindowTitle("Reference Name Error")
                msg.setText("A Reference genome with the same name already exists!")
                msg.setIcon(msg.Warning)
                x = msg.exec_()
            else:
                self.config["refGenomes_list"] += [self.addRef.Refname_lineEdit.text()]
                self.config[self.addRef.Refname_lineEdit.text()] = { 
                    "fasta":self.addRef.path_lineEdit.text(),
                    "dict":self.addRef.ref_dict,
                    "version":self.addRef.version_lineEdit.text(),
                    "tags":"reference"}
                self.addRef.close()
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)
                self.ref_listWidget.addItem(self.addRef.Refname_lineEdit.text())
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("DB Name Error")
            msg.setText("Every Reference Genome needs a name!\nSet the Ref name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()

    def retrieve_ref_infos(self):
        if self.addRef.Refname_lineEdit.text() != "":
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Save changes")
            msg.setText("Do you want to save changes?\n")
            msg.setIcon(msg.Warning)
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
            x = msg.exec_()
            if x == QMessageBox.Ok:
                old_ref = self.ref_listWidget.currentItem().text()
                new_ref = self.addRef.Refname_lineEdit.text()
                #print(self.config["tools_list"])
                index = self.config["refGenomes_list"].index(old_ref)
                self.config["refGenomes_list"][index] = new_ref
                del self.config[old_ref]

                self.config[new_ref] = { 
                    "fasta":self.addRef.path_lineEdit.text(),
                    "dict":self.addRef.ref_dict,
                    "version":self.addRef.version_lineEdit.text(),
                    "tags":"reference"}
                self.addRef.close()
                
                with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
                    json.dump(self.config, cfg, indent=4)
                self.ref_listWidget.currentItem().setText(new_ref)
                #elf.tool_listWidget.addItem(new_tool)
                #print(self.config["tools_list"])
## NEW INFO

    def init_add_new_info(self):
        self.add_info = at.Add_Info()
        self.add_info.show()
        self.add_info.Save_pushButton.clicked.connect(self.retrieve_new_info)
        self.add_info.Cancel_pushButton.clicked.connect(self.add_new_info_close)
        self.add_info.pathSearch_toolButton.clicked.connect(self.new_info_path_search)


    def add_new_info_close(self):
        self.add_info.close()

    def retrieve_new_info(self):
        if self.add_info.Refname_lineEdit.text() != "":
            self.config[self.clicked][self.add_info.Refname_lineEdit.text()] = self.add_info.path_lineEdit.text()
            self.add_info.close()
            n_row = self.tableWidget.rowCount()
            self.tableWidget.setRowCount(n_row+1)
            new_row = QtWidgets.QTableWidgetItem(self.add_info.Refname_lineEdit.text())
            self.tableWidget.setVerticalHeaderItem (n_row, new_row)          
            new_item = QtWidgets.QTableWidgetItem(self.add_info.path_lineEdit.text())
            self.tableWidget.setItem(n_row, 0, new_item)
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("DB Name Error")
            msg.setText("Every Information needs a name!\nSet the Info name pls.")
            msg.setIcon(msg.Warning)
            x = msg.exec_()


    def delete_info(self):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Delete Information")
        msg.setText("Do you want to delete this Info?")
        msg.setIcon(msg.Question)  
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:
            index = self.tableWidget.selectedIndexes()
            self.tableWidget.removeRow(index[0].row())

            

## others

    def save_settings(self):
        self.config[self.clicked] = dict()
        for index in range(self.tableWidget.rowCount()):
            print(self.tableWidget.verticalHeaderItem(index).text(), self.tableWidget.item(index,0).text())
            self.config[self.clicked][self.tableWidget.verticalHeaderItem(index).text()] = self.tableWidget.item(index,0).text()
        with open(self.configs_folder + '/tools_cfg/tools.cfg', 'w') as cfg:
            json.dump(self.config, cfg, indent=4)

    def tool_path_search(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"", os.path.expanduser("~"), options=options)
        if file:
            self.addTool.path_lineEdit.setText(file)

    def DB_path_search(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"", os.path.expanduser("~"), options=options)
        if file:
            self.addDB.path_lineEdit.setText(file)

    def Ref_path_search(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"", os.path.expanduser("~"), options=options)
        if file:
            ref_dict = ".".join(file.split('.')[:-1] + ['dict'])            
            self.addRef.path_lineEdit.setText(file)
            if os.path.isfile(ref_dict):
                self.addRef.ref_dict = ref_dict

    def new_info_path_search(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"", os.path.expanduser("~"), options=options)
        if file:           
            self.add_info.path_lineEdit.setText(file)


    def show_Info_Menu(self, event):
       
            menu = QtWidgets.QMenu()
            add_Action = menu.addAction("Add Info")
            delete_Action = menu.addAction("Delete Info")
            #modify_Action = menu.addAction("Modify Info")
            action = menu.exec_(self.mapToGlobal(QCursor.pos()))

            # if action == modify_Action:            
            #     for index in self.tableWidget.selectedIndexes():            
            #         print('onRightClick selected index.row: %s, selected index.column: %s' % (index.row(), index.column()))
            #         menu.close()
            if action == add_Action:
                self.init_add_new_info()
            elif action == delete_Action:
                self.delete_info()
       