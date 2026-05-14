# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/pipeline_designer.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
#from os.path import expanduser
import os.path
import subprocess
import json
import glob



class Pipeline_designer(QtWidgets.QWidget):

    def __init__(self, parent = None):
        super(Pipeline_designer, self).__init__(parent)
        self.setupUi()
        self.init_functions()

    def remove_tool(self):
        try:
            tool = self.tool_listWidget.currentItem()
            for rowindex in range(0,self.step_tableWidget.rowCount()):
                if 'tool' in self.step_tableWidget.verticalHeaderItem(rowindex).text():
                    if tool.text() in self.step_tableWidget.item(rowindex, 0).text().split(','):   
                        msg = QtWidgets.QMessageBox()
                        msg.setWindowTitle("Delete tool")
                        msg.setText("Do you want to romove this tool?")
                        msg.setIcon(msg.Question)
                        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
                        x = msg.exec_()
                        if x == QMessageBox.Ok:
                            self.init_treewidget_tool()
                            if self.step_tableWidget.verticalHeaderItem(rowindex).text() == 'tool':
                                self.step_tableWidget.setItem(rowindex, 0, QtWidgets.QTableWidgetItem(""))
                            elif self.step_tableWidget.verticalHeaderItem(rowindex).text() == 'tools':
                                itemlist = self.step_tableWidget.item(rowindex, 0).text().split(',')
                                itemlist.remove(tool.text())
                                item = ','.join(itemlist)
                                self.step_tableWidget.setItem(rowindex, 0, QtWidgets.QTableWidgetItem(item))
        except Exception as E:
            print(E)
            pass            

    def add_tool(self):
        tool = self.tool_listWidget.currentItem()
        for rowindex in range(0,self.step_tableWidget.rowCount()):
            if self.step_tableWidget.verticalHeaderItem(rowindex).text() == 'tool':
                self.step_tableWidget.setItem(rowindex, 0, QtWidgets.QTableWidgetItem(tool.text()))
            elif self.step_tableWidget.verticalHeaderItem(rowindex).text() == 'tools':
                item = self.step_tableWidget.item(rowindex, 0).text().split(',')
                if item == [""]:
                    item = []
                if tool.text() not in item:
                    item += [tool.text()]
                self.step_tableWidget.setItem(rowindex, 0, QtWidgets.QTableWidgetItem(','.join(item)))

        self.init_treewidget_tool()

    def save_pipeline(self):
        current_pip_name = self.pipeline_comboBox.currentText()
        if current_pip_name == '-' or current_pip_name == 'default':
            current_pip_name = 'new_pipeline'
        text, ok = QInputDialog.getText(self, 'Do you want to save your pipeline?', 'Enter your pipeline name:',text=current_pip_name)
        current_pip_name = '_'.join(text.split(' '))
        path = self.configs_folder + '/pipelines/' + current_pip_name + '.pipeline'

        if ok:                    
            if os.path.exists(path):
                msg = QtWidgets.QMessageBox()
                msg.setWindowTitle("Pipeline "+ current_pip_name + " already exists.")
                msg.setText("Do you want to overwrite this pipeline?")
                msg.setIcon(msg.Question)
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
                x = msg.exec_()
                if x == QMessageBox.Ok:
                    self.new_pipeline["id"]=text
                    with open(path, 'w') as ss:
                        json.dump(self.new_pipeline, ss, indent=4)                
            else:
                self.new_pipeline["id"]=text
                with open(path, 'w') as ss:
                    json.dump(self.new_pipeline, ss, indent=4)
           

            i = self.pipeline_comboBox.findText(current_pip_name)
            if i == -1:
                self.pipeline_comboBox.addItem(current_pip_name)
                i = self.pipeline_comboBox.findText(current_pip_name)

            self.pipeline_comboBox.setCurrentIndex(i)


    def cancel_pipeline(self):
        current_pip_name = self.pipeline_comboBox.currentText()
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Pipeline "+ current_pip_name)
        msg.setText("Do you want to cancel your changes?")
        msg.setIcon(msg.Question)
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:
            starting_folder = self.configs_folder + '/pipelines/'
            if self.old_pipeline_name == '-':
                old_pipeline_name = 'default'
                self.new_pipeline = json.loads((open(starting_folder+'/'+ old_pipeline_name  + '.pipeline').read()).encode('utf8'))
            else:
                self.new_pipeline = json.loads((open(starting_folder+'/'+ self.old_pipeline_name  + '.pipeline').read()).encode('utf8'))
            self.init_analysis_comboBox()
            self.init_variables()
            self.init_treewidget_checkstate()
            self.init_ref_comboBox()
            self.init_treewidget_tool()


    def delete_pipeline(self):
        current_pip_name = self.pipeline_comboBox.currentText()
        if current_pip_name == '-' or current_pip_name == 'default':
            pass
        else:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Delete " +current_pip_name + " pipeline?" )
            msg.setText("Do you want to delete this pipeline?")
            msg.setIcon(msg.Question)
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
            x = msg.exec_()
            if x == QMessageBox.Ok:
                filetodelete = self.configs_folder + '/pipelines/'+current_pip_name+'.pipeline'
                os.remove(filetodelete)
                self.init_pipeline_comboBox()

    def step_info_change(self, item):
        STEP = self.dict_steps[self.label.text()]["STEP"]
        step = self.dict_steps[self.label.text()]["step"]
        row = self.step_tableWidget.row(item)
        info = self.step_tableWidget.verticalHeaderItem(row).text()
        #dict_info{"Threads":"threads",'RAM':"ram"}
        if item.text() != '':
            if STEP==step:
                if step == "variantcalling" or step == "cnvcalling" :
                    if info == "min_base_quality_score" or info == "min_alt_coverage" or info == "min_alt_freq" or info == "min_mapping_quality_score":
                        self.new_pipeline[step]['filters'][info]=item.text()
                    elif info == 'tools':
                        self.new_pipeline[step][info]=item.text().split(',')
                    else:
                        self.new_pipeline[step][info]=item.text()
                else:
                    self.new_pipeline[step][info]=item.text()
            else:
                if step == "variantcalling" or step == "cnvcalling" :
                    if info == "min_base_quality_score" or info == "min_alt_coverage" or info == "min_alt_freq" or info == "min_mapping_quality_score":
                        self.new_pipeline[STEP][step]['filters'][info]=item.text()
                    elif info == 'tools':
                        self.new_pipeline[STEP][step][info]=item.text().split(',')
                    else:
                        self.new_pipeline[STEP][step][info]=item.text()
                else:
                    self.new_pipeline[STEP][step][info]=item.text()
        else:
            if STEP==step:
                if step == "variantcalling" or step == "cnvcalling" :
                    if info == "min_base_quality_score" or info == "min_alt_coverage" or info == "min_alt_freq" or info == "min_mapping_quality_score":
                        self.new_pipeline[step]['filters'][info]=''
                    elif info == 'tools':
                        self.new_pipeline[step][info]=[]
                    else:
                        self.new_pipeline[step][info]=''
                else:
                    self.new_pipeline[step][info]=''
            else:
                if step == "variantcalling" or step == "cnvcalling" :
                    if info == "min_base_quality_score" or info == "min_alt_coverage" or info == "min_alt_freq" or info == "min_mapping_quality_score":
                        self.new_pipeline[STEP][step]['filters'][info]=''
                    elif info == 'tools':
                        self.new_pipeline[STEP][step][info]=[]
                    else:
                        self.new_pipeline[STEP][step][info]=''
                else:
                    self.new_pipeline[STEP][step][info]=''

    def tool_info_change(self, item):
        STEP = self.dict_steps[self.label.text()]["STEP"]
        step = self.dict_steps[self.label.text()]["step"]
        tool = self.tool_listWidget.currentItem()
        row = self.tool_tableWidget.row(item)
        info = self.tool_tableWidget.verticalHeaderItem(row).text()

        if item.text() != "":
            if STEP==step:
                if tool.text() in self.new_pipeline[STEP].keys():
                    if info == "args":
                        self.new_pipeline[STEP][tool.text()][info]=item.text().split(',')
                    else:
                        self.new_pipeline[STEP][tool.text()][info]=item.text()
                else:
                    if info == "args":
                        self.new_pipeline[STEP][tool.text()]= {info:item.text().split(',')}
                    else:
                        self.new_pipeline[STEP][tool.text()]= {info:item.text()}
            else:
                if tool.text() in self.new_pipeline[STEP][step].keys():
                    if info == "args":
                        self.new_pipeline[STEP][step][tool.text()][info]=item.text().split(',')
                    else:
                        self.new_pipeline[STEP][step][tool.text()][info]=item.text()
                else:
                    if info == "args":
                        self.new_pipeline[STEP][step][tool.text()]= {info:item.text().split(',')}
                    else:
                        self.new_pipeline[STEP][step][tool.text()]= {info:item.text()}
        else:
            if STEP==step:
                if tool.text() in self.new_pipeline[STEP].keys():
                    if info == "args":
                        self.new_pipeline[STEP][tool.text()][info]=[]
                    else:
                        self.new_pipeline[STEP][tool.text()][info]=""
                else:
                    if info == "args":
                        self.new_pipeline[STEP][tool.text()]= {info:[]}
                    else:
                        self.new_pipeline[STEP][tool.text()]= {info:""}
            else:
                if tool.text() in self.new_pipeline[STEP][step].keys():
                    if info == "args":
                        self.new_pipeline[STEP][step][tool.text()][info]=[]
                    else:
                        self.new_pipeline[STEP][step][tool.text()][info]=""
                else:
                    if info == "args":
                        self.new_pipeline[STEP][step][tool.text()]= {info:[]}
                    else:
                        self.new_pipeline[STEP][step][tool.text()]= {info:""}

    def showStepSetting_and_Tools(self,step):
        self.tool_listWidget.clear()
        self.tool_tableWidget.setRowCount(0)
        self.step_tableWidget.setColumnCount(1)
        self.step_tableWidget.setRowCount(0)
        
        
        try: 
            tool_list = []          
            if step == "Pre-Alignment":
                self.step_tableWidget.setRowCount(2)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["ram"]))            
            if step == "Adapters trimming":
                tool_list = self.tools_cfg["tools"]["trim_adapters"]
                self.step_tableWidget.setRowCount(3)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("adapter1"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("adapter2"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("tool"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["trim_adapters"]["adapter1"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["trim_adapters"]["adapter2"]))              
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["trim_adapters"]["tool"]))

            if step == "FASTQ read lenght filter":
                tool_list = self.tools_cfg["tools"]["filter_fastq"]
                self.step_tableWidget.setRowCount(3)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("maxlen"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("minlen"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("tool"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["filter_fastq_by_len"]["maxlen"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["filter_fastq_by_len"]["minlen"]))               
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["filter_fastq_by_len"]["tool"]))
            
            if step == "FASTQ quality filter":
                tool_list = self.tools_cfg["tools"]["filter_fastq"]
                self.step_tableWidget.setRowCount(2)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("quality"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("tool"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["filter_fastq_by_qual"]["base_quality"]))              
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["filter_fastq_by_qual"]["tool"]))

            if step == "FASTQ quality control":
                self.STEP = "prealignment"
                tool_list = self.tools_cfg["tools"]["fastq_QC"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))               
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["prealignment"]["fastq_QC"]["tool"]))
            
            if step == "Alignment":
                self.step_tableWidget.setRowCount(2)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["ram"]))
            if step == "UMI/Molecular barcodes merge":
                self.STEP = "alignment"
                tool_list = self.tools_cfg["tools"]["merge_UMI"]
            if step == "FASTQ alignment":
                tool_list = self.tools_cfg["tools"]["fastq_alignment"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))             
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["fastq_alignment"]["tool"]))
            if step == "SAM to BAM convertion":
                self.STEP = "alignment"
                tool_list = self.tools_cfg["tools"]["sam_to_bam"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))             
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["sam_to_bam"]["tool"]))
            if step == "BAM sort":
                self.STEP = "alignment"
                tool_list = self.tools_cfg["tools"]["sortSam"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))             
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["sortSam"]["tool"]))
            if step == "BAM quality control":
                self.STEP = "alignment"
                tool_list = self.tools_cfg["tools"]["bam_QC"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))             
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["alignment"]["bam_QC"]["tool"]))
            
            if step == "Pre-Processing":
                self.step_tableWidget.setRowCount(2)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["ram"]))
            if step == "BAM filter":
                tool_list = self.tools_cfg["tools"]["filter_bam"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["filter_bam"]["tool"]))
            if step == "Add readgroups to BAM":
                tool_list = self.tools_cfg["tools"]["add_readgroups"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["add_readgroups"]["tool"]))
            if step == "PCR duplicates marking":
                tool_list = self.tools_cfg["tools"]["mark_pcr_dup"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["mark_pcr_dup"]["tool"]))
            if step == "InDels realignment":
                tool_list = self.tools_cfg["tools"]["indel_realignment"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["indel_realignment"]["tool"]))
            if step == "Base quality recalibration":
                tool_list = self.tools_cfg["tools"]["BQ_recalibration"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["preprocessing"]["BQ_recalibration"]["tool"]))
            
    #            if step == "Variant Calling":
            if step == "VC SNV & short InDels":
                tool_list = self.tools_cfg["tools"]["variantcalling"]
                self.step_tableWidget.setRowCount(8)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("samples_org"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setVerticalHeaderItem(3,QtWidgets.QTableWidgetItem("min_base_quality_score"))
                self.step_tableWidget.setVerticalHeaderItem(4,QtWidgets.QTableWidgetItem("min_alt_coverage"))  
                self.step_tableWidget.setVerticalHeaderItem(5,QtWidgets.QTableWidgetItem("min_alt_freq"))
                self.step_tableWidget.setVerticalHeaderItem(6,QtWidgets.QTableWidgetItem("min_mapping_quality_score"))
                self.step_tableWidget.setVerticalHeaderItem(7,QtWidgets.QTableWidgetItem("tools"))
   
                try:
                    sample_org_item = QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["samples_organization"])
                except:
                    sample_org_item = QtWidgets.QTableWidgetItem('single-sample')
                try:
                    self.step_tableWidget.doubleClicked.disconnect()
                    self.step_tableWidget.doubleClicked.connect(self.sampleOrg_doubleClicked)
                except:
                    pass

                self.step_tableWidget.setItem(0, 0, sample_org_item)
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["threads"]))
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["ram"]))             
                self.step_tableWidget.setItem(3, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["filters"]["min_base_quality_score"]))
                self.step_tableWidget.setItem(4, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["filters"]["min_alt_coverage"]))               
                self.step_tableWidget.setItem(5, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["filters"]["min_alt_freq"]))                
                self.step_tableWidget.setItem(6, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variantcalling"]["filters"]["min_mapping_quality_score"]))                          
                self.step_tableWidget.setItem(7, 0, QtWidgets.QTableWidgetItem(','.join(self.new_pipeline["variantcalling"]["tools"])))
            
            if step == "VC Copy Number Variation":
                tool_list = self.tools_cfg["tools"]["cnvcalling"]
                self.step_tableWidget.setRowCount(4)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("samples_org"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setVerticalHeaderItem(3,QtWidgets.QTableWidgetItem("tools"))
                try:
                    sample_org_item = QtWidgets.QTableWidgetItem(self.new_pipeline["cnvcalling"]["samples_organization"])
                except:
                    sample_org_item = QtWidgets.QTableWidgetItem('single-sample')

                try:
                    self.step_tableWidget.doubleClicked.disconnect()
                    self.step_tableWidget.doubleClicked.connect(self.sampleOrg_doubleClicked)
                except:
                    pass
                self.step_tableWidget.setItem(0, 0, sample_org_item)
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["cnvcalling"]["threads"]))
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["cnvcalling"]["ram"]))             
                self.step_tableWidget.setItem(3, 0, QtWidgets.QTableWidgetItem(','.join(self.new_pipeline["cnvcalling"]["tools"])))
            
                
            
            if step == "Post-Processing":
                self.step_tableWidget.setRowCount(2)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["postprocessing"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["postprocessing"]["ram"]))           
            
            if step == "VCF filter":
                tool_list = self.tools_cfg["tools"]["vcf_filter"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["postprocessing"]["vcf_filter"]["tool"]))
            if step == "VCF normalization":
                tool_list = self.tools_cfg["tools"]["vcf_norm"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))              
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["postprocessing"]["vcf_norm"]["tool"]))
                    
            if step == "Ann SNV & short InDels":
                tool_list = self.tools_cfg["tools"]["variant_ann"]
                self.step_tableWidget.setRowCount(3)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("tool"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variant_annotation"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variant_annotation"]["ram"]))              
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["variant_annotation"]["tool"]))

            if step == "Ann Copy Number Variation":
                tool_list = self.tools_cfg["tools"]["cnv_ann"]
                self.step_tableWidget.setRowCount(3)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("threads"))
                self.step_tableWidget.setVerticalHeaderItem(1,QtWidgets.QTableWidgetItem("ram"))
                self.step_tableWidget.setVerticalHeaderItem(2,QtWidgets.QTableWidgetItem("tool"))
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["cnv_annotation"]["threads"]))
                self.step_tableWidget.setItem(1, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["cnv_annotation"]["ram"]))              
                self.step_tableWidget.setItem(2, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["cnv_annotation"]["tool"]))

            if step == "Annotation filter":
                tool_list = self.tools_cfg["tools"]["ann_filter"]
                self.step_tableWidget.setRowCount(1)
                self.step_tableWidget.setVerticalHeaderItem(0,QtWidgets.QTableWidgetItem("tool"))        
                self.step_tableWidget.setItem(0, 0, QtWidgets.QTableWidgetItem(self.new_pipeline["postannotation"]["ann_filter"]["tool"]))

            if step == "Ann transcripts filter":
                tool_list = self.tools_cfg["tools"]["trs_filter"]
             
            if step == "Annotated VCF to TSV convertion":
                tool_list = self.tools_cfg["tools"]["ann_vcf_to_tsv"]


            if len(tool_list) > 0:
                #print(tool_list)
                self.tool_listWidget.clear()
                for tool in tool_list:
                    item = QtWidgets.QListWidgetItem(tool)
                    self.tool_listWidget.addItem(item)


                    #item.setText(tool)

        except Exception as e:
            print(e)
            success = QMessageBox()
            success.setWindowTitle('Tools cfg file ERROR')
            success.setText('Please choose a tools configuration file')
            #success.setText(e)
            success.setIcon(QMessageBox.Critical)
            success.exec()      

    def sampleOrg_doubleClicked(self, item):
        clickeditem = self.step_tableWidget.item(item.row(),item.column())
        step = self.dict_steps[self.label.text()]["step"]
        if self.step_tableWidget.verticalHeaderItem(item.row()).text() == 'samples_org':

            def return_org():
                self.step_tableWidget.item(item.row(),item.column()).setText(self.prova.comboBox.currentText())
                self.prova.close()
          
            class Org_list(QDialog):
                
                def setupUi(self,step):
                    self.setObjectName("Form")
                    self.resize(367, 121)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
                    self.setSizePolicy(sizePolicy)
                    self.verticalLayout = QtWidgets.QVBoxLayout(self)
                    self.verticalLayout.setObjectName("verticalLayout")
                    self.frame = QtWidgets.QFrame(self)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
                    self.frame.setSizePolicy(sizePolicy)
                    self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
                    self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
                    self.frame.setObjectName("frame")
                    self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.frame)
                    self.verticalLayout_2.setObjectName("verticalLayout_2")
                    self.label = QtWidgets.QLabel(self.frame)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
                    self.label.setSizePolicy(sizePolicy)
                    self.label.setObjectName("label")
                    self.verticalLayout_2.addWidget(self.label)
                    self.comboBox = QtWidgets.QComboBox(self.frame)
                    self.comboBox.setObjectName("comboBox")
                    self.verticalLayout_2.addWidget(self.comboBox)
                    self.buttonBox = QtWidgets.QDialogButtonBox(self.frame)
                    self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
                    self.buttonBox.setObjectName("buttonBox")
                    self.verticalLayout_2.addWidget(self.buttonBox)
                    self.verticalLayout.addWidget(self.frame)
                    if step == "variantcalling":
                        self.comboBox.addItem('single-sample')
                        self.comboBox.addItem('cohort')
                        self.comboBox.addItem('case-control')
                        self.comboBox.addItem('trio')
                    
                    elif step == "cnvcalling":
                        self.comboBox.addItem('single-sample')
                        self.comboBox.addItem('cohort')

                    self.retranslateUi()
                    QtCore.QMetaObject.connectSlotsByName(self)
                    #elf.buttonBox.accepted.connect(self.close)
                    self.buttonBox.rejected.connect(self.close)
                    

                def retranslateUi(self):
                    _translate = QtCore.QCoreApplication.translate
                    self.setWindowTitle(_translate("Form", ""))
                    self.label.setText(_translate("Form", "Set Samples Organization"))

            self.prova = Org_list()
            self.prova.setupUi(step)
            self.prova.buttonBox.accepted.connect(return_org)
            self.prova.exec()
            #self.prova.buttonBox.rejected.connect(close_widg())
        
    def onTreeItemClicked(self, it, col):
        #print(it, col, it.text(col))
        self.label.setText(it.text(col))
        self.showStepSetting_and_Tools(it.text(col))

        #self.showInfo(it.text(col))
        #self.showTools(it.text(col))
    def onTreeItemActivated(self, it, col):

        parent = it.parent()
       #print('prima',self.new_pipeline["workflow"])

        if it.text(0) != 'Variant Calling' and it.text(0) != 'Annotation' \
            and it.text(0) != "VC SNV & short InDels" and it.text(0) != "VC Copy Number Variation" \
            and it.text(0) != "Ann SNV & short InDels" and it.text(0) != "Ann Copy Number Variation":
            step = self.dict_steps[it.text(0)]['step']
            STEP = self.dict_steps[it.text(0)]['STEP']
            #print('dopo',self.new_pipeline[STEP]["workflow"])
            STEP_workflow = self.new_pipeline["workflow"]
            step_workflow = self.new_pipeline[STEP]["workflow"]
            if parent != None:
                if it.checkState(0) != 0:
                    if step not in step_workflow:
                        step_workflow += [step]
                else:
                    if step in step_workflow:
                        step_workflow.remove(step)
                if parent.checkState(0) != 0:
                    #print('prima',self.new_pipeline["workflow"])
                    if STEP not in STEP_workflow:
                        STEP_workflow += [STEP]
                else:

                    if STEP in STEP_workflow:
                        STEP_workflow.remove(STEP)        
            else:
                if it.checkState(0) != 0:
                    if STEP not in STEP_workflow:
                        STEP_workflow += [STEP]
                else:
                    if STEP in STEP_workflow:
                        STEP_workflow.remove(STEP)
            
            self.new_pipeline[STEP]["workflow"] = step_workflow 
            self.new_pipeline["workflow"] = STEP_workflow

            #print('dopo',self.new_pipeline[STEP]["workflow"])
            
        elif it.text(0) != 'Variant Calling' and it.text(0) != 'Annotation':
            STEP_workflow = self.new_pipeline["workflow"]
            STEP = self.dict_steps[it.text(0)]['STEP']
           
            if parent != None:
                if it.checkState(0) != 0:
                    if STEP not in STEP_workflow:
                        STEP_workflow += [STEP]
                else:
                    if STEP in STEP_workflow:
                        STEP_workflow.remove(STEP)
                    if STEP in STEP_workflow:
                        STEP_workflow.remove(STEP)        
            self.new_pipeline["workflow"] = STEP_workflow

        #print('dopo',self.new_pipeline["workflow"])

    def onToolItemClicked(self, it):

        self.tool_tableWidget.setColumnCount(1)
        self.tool_tableWidget.setRowCount(0)
        tool = it.text()

        STEP = self.dict_steps[self.label.text()]["STEP"]
        step = self.dict_steps[self.label.text()]["step"]
        try:
            if STEP != step:
                toolargs = self.new_pipeline[STEP][step][tool]
            else:
                toolargs = self.new_pipeline[STEP][tool]
        except:
            toolargs = {"args":[]}

        to_add=[]
        #print(STEP,step ,toolargs)
        
        for info in toolargs.keys():
            header_item = QtWidgets.QTableWidgetItem(info)
            if type(toolargs[info]) is list:
                #print(toolargs[info])      
                value_item = QtWidgets.QTableWidgetItem(','.join(toolargs[info]))
            elif type(toolargs[info]) is dict:
                pass
            else:
                 value_item = QtWidgets.QTableWidgetItem(toolargs[info])
            to_add += [[header_item,value_item]]
        self.tool_tableWidget.setRowCount(len(to_add))
        i=0
        for item in to_add:
            self.tool_tableWidget.setVerticalHeaderItem(i,item[0])
            self.tool_tableWidget.setItem(i, 0, item[1])
            i+=1

    def onToolItemDoubleClicked(self, item):
            clickeditem = self.tool_tableWidget.item(item.row(),item.column())
            
            class ArgsText(QDialog):
                def setupUi(self,i):
                    self.texttoargs = ' '.join(i.text().split(','))
                    self.i = i

                    self.setObjectName("Dialog")
                    self.resize(615, 491)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
                    self.setSizePolicy(sizePolicy)
                    self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                    self.verticalLayout = QtWidgets.QVBoxLayout(self)
                    self.verticalLayout.setObjectName("verticalLayout")
                    self.label = QtWidgets.QLabel(self)
                    self.label.setCursor(QtGui.QCursor(QtCore.Qt.SizeBDiagCursor))
                    self.label.setMouseTracking(True)
                    self.label.setObjectName("label")
                    self.verticalLayout.addWidget(self.label)
                    self.textEdit = QtWidgets.QTextEdit(self)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.textEdit.sizePolicy().hasHeightForWidth())
                    self.textEdit.setSizePolicy(sizePolicy)
                    self.textEdit.setObjectName("textEdit")
                    self.verticalLayout.addWidget(self.textEdit)
                    self.buttonBox = QtWidgets.QDialogButtonBox(self)
                    self.buttonBox.setEnabled(True)
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(self.buttonBox.sizePolicy().hasHeightForWidth())
                    self.buttonBox.setSizePolicy(sizePolicy)
                    self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
                    self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
                    self.buttonBox.setCenterButtons(False)
                    self.buttonBox.setObjectName("buttonBox")
                    self.verticalLayout.addWidget(self.buttonBox)

                    self.retranslateUi()
                    self.buttonBox.accepted.connect(self.accept)
                    self.buttonBox.rejected.connect(self.reject)
                    QtCore.QMetaObject.connectSlotsByName(self)

                    self.textEdit.setText(self.texttoargs)
                    self.exec()

                def accept(self):
                    self.texttoargs = self.textEdit.toPlainText()
                    #self.i.setText(self.texttoargs)
                    self.close()

                def retranslateUi(self):
                    _translate = QtCore.QCoreApplication.translate
                    self.setWindowTitle(_translate("Dialog", "Dialog"))
                    self.label.setText(_translate("Dialog", "TextLabel"))

            #def _logInfoWidget(self):
            text = ''
            prova = ArgsText()
            prova.setupUi(clickeditem)
            text = ','.join(','.join(prova.texttoargs.split('\n')).split(' '))
            clickeditem.setText(text)
            
        #row = self.tool_tableWidget.row(it)
        #info = self.step_tableWidget.verticalHeaderItem(row).text()
    def on_pipeline_combobox_changed(self, value):
        if self.pipeline_comboBox.currentText() != self.old_pipeline_name:
            #print("combobox changed", value)
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle("Changing Pipeline")
            msg.setText("Do you want to save changes before open other pipeline settings?")
            msg.setIcon(msg.Question)  
            msg.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel); 
            x = msg.exec_()
            self.new_pipeline_name = self.pipeline_comboBox.currentText()
            starting_folder = self.configs_folder + '/pipelines/'
            if self.new_pipeline_name != '-':
                new_pipeline_name = self.new_pipeline_name
            else:
                new_pipeline_name = 'default'
            if x == QMessageBox.Save:
                self.save_pipeline()
                self.old_pipeline_index = self.pipeline_comboBox.currentIndex()
                self.old_pipeline_name = self.pipeline_comboBox.currentText()
                self.new_pipeline = json.loads((open(starting_folder+ '/' + new_pipeline_name + '.pipeline').read()).encode('utf8'))
                #self.init_analysis_comboBox()
                i = self.ref_comboBox.findText(self.new_pipeline['reference_version'])
                self.ref_comboBox.setCurrentIndex(i)             

                try:
                    i = self.analysis_comboBox.findText(self.new_pipeline['analysis'])
                    self.analysis_comboBox.setCurrentIndex(i)
                except:
                    pass
                self.init_variables()
                self.init_treewidget_checkstate()
                self.init_treewidget_tool()
            elif x == QMessageBox.Discard:
                self.old_pipeline_index = self.pipeline_comboBox.currentIndex()
                self.old_pipeline_name = self.pipeline_comboBox.currentText()
                self.new_pipeline = json.loads((open(starting_folder+ '/' + new_pipeline_name + '.pipeline').read()).encode('utf8'))

                #self.init_variables()
                self.init_treewidget_checkstate()
                #self.init_treewidget_tool()

                i = self.ref_comboBox.findText(self.new_pipeline['reference_version'])
                self.ref_comboBox.setCurrentIndex(i)
                #print(self.new_pipeline['reference_version'],i)


                try:
                    i = self.analysis_comboBox.findText(self.new_pipeline['analysis'])
                    self.analysis_comboBox.setCurrentIndex(i)
                except:
                    pass
            elif x == QMessageBox.Cancel:
                pass

    def on_ref_combobox_changed(self, value):
            self.new_pipeline["reference_version"] = value
            #print("ref changed", value)

    def on_analysis_combobox_changed(self, value):
            self.new_pipeline["analysis"] = value
            #print("analysis changed", value)

    def setupUi(self):
        self.setObjectName("Pipeline_designer")
        self.resize(1017, 890)

        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizePolicy)

        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")

        self.mframe = QtWidgets.QFrame(self)
        self.mframe.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.mframe.setFrameShadow(QtWidgets.QFrame.Raised)
        self.mframe.setObjectName("mframe")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.mframe)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.frame_2 = QtWidgets.QFrame(self.mframe)
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.frame_2)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label = QtWidgets.QLabel(self.frame_2)
        self.label.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setTextFormat(QtCore.Qt.AutoText)
        self.label.setScaledContents(True)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setWordWrap(False)
        self.label.setObjectName("label")

        self.verticalLayout_3.addWidget(self.label)

        self.step_tableWidget = QtWidgets.QTableWidget(self.frame_2)
        self.step_tableWidget.setObjectName("step_tableWidget")
        self.step_tableWidget.setColumnCount(1)
        self.step_tableWidget.setRowCount(0)
        #self.step_tableWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        item = QtWidgets.QTableWidgetItem()

        item.setText("Step Settings")
        self.step_tableWidget.setHorizontalHeaderItem(0, item)
        self.step_tableWidget.horizontalHeader().setStretchLastSection(True)
        self.step_tableWidget.verticalHeader().setCascadingSectionResizes(False)
        self.step_tableWidget.verticalHeader().setDefaultSectionSize(32)
        self.verticalLayout_3.addWidget(self.step_tableWidget)

        self.frame_6 = QtWidgets.QFrame(self.frame_2)
        self.frame_6.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_6.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_6.setObjectName("frame_6")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout(self.frame_6)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.useTool_pushButton = QtWidgets.QPushButton(self.frame_6)
        self.useTool_pushButton.setObjectName("useTool_pushButton")
        self.horizontalLayout_3.addWidget(self.useTool_pushButton)
        self.removeTool_pushButton = QtWidgets.QPushButton(self.frame_6)
        self.removeTool_pushButton.setObjectName("removeTool_pushButton")
        self.horizontalLayout_3.addWidget(self.removeTool_pushButton)
        self.verticalLayout_3.addWidget(self.frame_6)

        self.tool_listWidget = QtWidgets.QListWidget(self.frame_2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tool_listWidget.sizePolicy().hasHeightForWidth())
        self.tool_listWidget.setSizePolicy(sizePolicy)
        self.tool_listWidget.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.tool_listWidget.setObjectName("tool_listWidget")
        self.verticalLayout_3.addWidget(self.tool_listWidget)

        self.tool_tableWidget = QtWidgets.QTableWidget(self.frame_2)
        self.tool_tableWidget.setObjectName("tool_tableWidget")
        self.tool_tableWidget.setColumnCount(1)
        self.tool_tableWidget.setRowCount(0)
        self.tool_tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tool_tableWidget.verticalHeader().setCascadingSectionResizes(False)
        self.tool_tableWidget.verticalHeader().setDefaultSectionSize(32)
        item = QtWidgets.QTableWidgetItem()
        item.setText("Tool Settings")
        self.tool_tableWidget.setHorizontalHeaderItem(0, item)
        self.verticalLayout_3.addWidget(self.tool_tableWidget)

        
        self.gridLayout_2.addWidget(self.frame_2, 3, 1, 2, 1)
        

        self.frame_4 = QtWidgets.QFrame(self.mframe)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_4.sizePolicy().hasHeightForWidth())
        self.frame_4.setSizePolicy(sizePolicy)
        self.frame_4.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_4.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_4.setObjectName("frame_4")
        self.gridLayout = QtWidgets.QGridLayout(self.frame_4)
        self.gridLayout.setObjectName("gridLayout")
        
        self.ref_comboBox = QtWidgets.QComboBox(self.frame_4)
        self.ref_comboBox.setObjectName("ref_comboBox")
        self.gridLayout.addWidget(self.ref_comboBox, 3, 8, 1, 1)

        self.tools_cfg_lineEdit = QtWidgets.QLineEdit(self.frame_4)
        self.tools_cfg_lineEdit.setObjectName("tools_cfg_lineEdit")
        self.gridLayout.addWidget(self.tools_cfg_lineEdit, 3, 1, 1, 1)

        self.tools_toolButton = QtWidgets.QToolButton(self.frame_4)
        self.tools_toolButton.setObjectName("toolButton")
        self.gridLayout.addWidget(self.tools_toolButton, 3, 2, 1, 2)
       

        self.Pipeline_name = QtWidgets.QLabel(self.frame_4)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.Pipeline_name.sizePolicy().hasHeightForWidth())
        self.Pipeline_name.setSizePolicy(sizePolicy)
        self.Pipeline_name.setObjectName("Pipeline_name")
        self.gridLayout.addWidget(self.Pipeline_name, 0, 0, 1, 1)
        
        self.ref_label = QtWidgets.QLabel(self.frame_4)
        self.ref_label.setObjectName("ref_label")
        self.gridLayout.addWidget(self.ref_label, 3, 6, 1, 1)

        self.analysis_label = QtWidgets.QLabel(self.frame_4)
        self.analysis_label.setObjectName("analysis_label")
        self.gridLayout.addWidget(self.analysis_label, 0, 4, 1, 1)

        self.analysis_comboBox = QtWidgets.QComboBox(self.frame_4)
        self.analysis_comboBox.setObjectName("analysis_comboBox")
        self.gridLayout.addWidget(self.analysis_comboBox, 0, 6, 1, 3)

        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 3, 4, 1, 1)



        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 3, 6, 1, 1)
        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem1, 3, 8, 1, 1)
        
        self.tools_label = QtWidgets.QLabel(self.frame_4)
        self.tools_label.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.tools_label.setObjectName("tools_label")
        self.gridLayout.addWidget(self.tools_label,3, 0, 1, 1)
        
        self.pipeline_comboBox = QtWidgets.QComboBox(self.frame_4)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(3)
        sizePolicy.setHeightForWidth(self.pipeline_comboBox.sizePolicy().hasHeightForWidth())
        self.pipeline_comboBox.setSizePolicy(sizePolicy)
        #self.pipeline_comboBox.setEditable(True)
        self.pipeline_comboBox.setObjectName("pipeline_comboBox")
        self.gridLayout.addWidget(self.pipeline_comboBox, 0, 1, 1, 3)
        
        self.gridLayout_2.addWidget(self.frame_4, 1, 0, 1, 2)
        self.horizontalLayout_2.addWidget(self.mframe)
        
        self.frame_3 = QtWidgets.QFrame(self.mframe)
        self.frame_3.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy)
        self.frame_3.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.frame_3.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")
        self.formLayout = QtWidgets.QFormLayout(self.frame_3)
        self.formLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        self.formLayout.setContentsMargins(9, -1, -1, -1)
        self.formLayout.setObjectName("formLayout")
        self.treeWidget = QtWidgets.QTreeWidget(self.frame_3)
        self.treeWidget.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.treeWidget.sizePolicy().hasHeightForWidth())
        self.treeWidget.setSizePolicy(sizePolicy)
        self.treeWidget.setMinimumSize(QtCore.QSize(461, 548))
        self.treeWidget.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.treeWidget.setAcceptDrops(False)
        self.treeWidget.setAutoFillBackground(True)
        self.treeWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.treeWidget.setTextElideMode(QtCore.Qt.ElideRight)
        self.treeWidget.setAutoExpandDelay(-1)
        self.treeWidget.setIndentation(20)
        self.treeWidget.setRootIsDecorated(True)
        self.treeWidget.setAnimated(True)
        self.treeWidget.setAllColumnsShowFocus(False)
        self.treeWidget.setHeaderHidden(False)
        self.treeWidget.setColumnCount(2)

        self.treeWidget.setObjectName("treeWidget")
        item_pre_alig = QtWidgets.QTreeWidgetItem(self.treeWidget)
        item_pre_alig.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_pre_alig.flags())
        item_adapt = QtWidgets.QTreeWidgetItem(item_pre_alig)
        item_adapt.setFlags(item_adapt.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_adapt.setCheckState(0, QtCore.Qt.Unchecked)
        item_len_filt = QtWidgets.QTreeWidgetItem(item_pre_alig)
        item_len_filt.setFlags(item_len_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_len_filt.setCheckState(0, QtCore.Qt.Unchecked)
        item_q_filt = QtWidgets.QTreeWidgetItem(item_pre_alig)
        item_q_filt.setFlags(item_q_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_q_filt.setCheckState(0, QtCore.Qt.Unchecked)
        item_fq_qc = QtWidgets.QTreeWidgetItem(item_pre_alig)
        item_fq_qc.setFlags(item_fq_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_fq_qc.setCheckState(0, QtCore.Qt.Unchecked)

        
        item_align = QtWidgets.QTreeWidgetItem(self.treeWidget)
        item_align.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_align.flags())      
        item_umi = QtWidgets.QTreeWidgetItem(item_align)
        item_umi.setFlags(item_umi.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_umi.setCheckState(0, QtCore.Qt.Unchecked)
        item_alig = QtWidgets.QTreeWidgetItem(item_align)
        item_alig.setFlags(item_alig.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_alig.setCheckState(0, QtCore.Qt.Unchecked)
        item_sambam = QtWidgets.QTreeWidgetItem(item_align)
        item_sambam.setFlags(item_sambam.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_sambam.setCheckState(0, QtCore.Qt.Unchecked)
        item_sort = QtWidgets.QTreeWidgetItem(item_align)
        item_sort.setFlags(item_sort.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_sort.setCheckState(0, QtCore.Qt.Unchecked)
        item_bam_qc = QtWidgets.QTreeWidgetItem(item_align)
        item_bam_qc.setFlags(item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_bam_qc.setCheckState(0, QtCore.Qt.Unchecked)

        item_pre_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)
        item_pre_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_pre_proc.flags())      
       
        item_bam_filt = QtWidgets.QTreeWidgetItem(item_pre_proc)
        item_bam_filt.setFlags(item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_bam_filt.setCheckState(0, QtCore.Qt.Unchecked)
        item_rgroup = QtWidgets.QTreeWidgetItem(item_pre_proc)
        item_rgroup.setFlags(item_rgroup.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_rgroup.setCheckState(0, QtCore.Qt.Unchecked)
        item_dup = QtWidgets.QTreeWidgetItem(item_pre_proc)
        item_dup.setFlags(item_dup.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_dup.setCheckState(0, QtCore.Qt.Unchecked)
        item_realig = QtWidgets.QTreeWidgetItem(item_pre_proc)
        item_realig.setFlags(item_realig.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_realig.setCheckState(0, QtCore.Qt.Unchecked)
        item_bqsr = QtWidgets.QTreeWidgetItem(item_pre_proc)
        item_bqsr.setFlags(item_bqsr.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_bqsr.setCheckState(0, QtCore.Qt.Unchecked)

        item_vcalling = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        item_vcalling.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_vcalling.flags())      
    
        item_shortv_call = QtWidgets.QTreeWidgetItem(item_vcalling)
        item_shortv_call.setFlags(item_shortv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_shortv_call.setCheckState(0, QtCore.Qt.Unchecked)
        item_cnv_call = QtWidgets.QTreeWidgetItem(item_vcalling)
        item_cnv_call.setFlags(item_cnv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_cnv_call.setCheckState(0, QtCore.Qt.Unchecked)

        item_post_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        item_post_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_post_proc.flags())      
    
        item_vcf_norm = QtWidgets.QTreeWidgetItem(item_post_proc)
        item_vcf_norm.setFlags(item_vcf_norm.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_vcf_norm.setCheckState(0, QtCore.Qt.Unchecked)
        item_vcf_filt = QtWidgets.QTreeWidgetItem(item_post_proc)
        item_vcf_filt.setFlags(item_vcf_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_vcf_filt.setCheckState(0, QtCore.Qt.Unchecked)
        item_vcf_to_tsv = QtWidgets.QTreeWidgetItem(item_post_proc)
        item_vcf_to_tsv.setFlags(item_vcf_to_tsv.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_vcf_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)
        # item_1 = QtWidgets.QTreeWidgetItem(item_post_proc)
        # item_shortv_call.setFlags(item_shortv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        # item_shortv_call.setCheckState(0, QtCore.Qt.Unchecked)

        item_ann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        item_ann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_ann.flags())      
    
        item_shortv_ann = QtWidgets.QTreeWidgetItem(item_ann)
        item_shortv_ann.setFlags(item_shortv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_shortv_ann.setCheckState(0, QtCore.Qt.Unchecked)
        item_cnv_ann = QtWidgets.QTreeWidgetItem(item_ann)
        item_cnv_ann.setFlags(item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_cnv_ann.setCheckState(0, QtCore.Qt.Unchecked)

        item_postann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        item_postann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|item_postann.flags())      
        
        item_filt_ann = QtWidgets.QTreeWidgetItem(item_postann)
        item_filt_ann.setFlags(item_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        item_trs_filt_ann = QtWidgets.QTreeWidgetItem(item_postann)
        item_trs_filt_ann.setFlags(item_trs_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_trs_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        item_vcf_ann_to_tsv = QtWidgets.QTreeWidgetItem(item_postann)
        item_vcf_ann_to_tsv.setFlags(item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        item_vcf_ann_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)
       
        self.treeWidget.header().setVisible(True)
        self.treeWidget.header().setCascadingSectionResizes(True)
        self.treeWidget.header().setDefaultSectionSize(300)
        self.treeWidget.header().setHighlightSections(False)
        self.treeWidget.header().setMinimumSectionSize(100)
        self.treeWidget.header().setSortIndicatorShown(False)
        self.treeWidget.header().setStretchLastSection(True)
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.SpanningRole, self.treeWidget)
        self.treeWidget.expandAll()
        self.gridLayout_2.addWidget(self.frame_3, 3, 0, 2, 1)
        self.horizontalLayout_2.addWidget(self.mframe)


        self.frame_5 = QtWidgets.QFrame(self.mframe)
        self.frame_5.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_5.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_5.setObjectName("frame_5")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.frame_5)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.cancel_pushButton = QtWidgets.QPushButton(self.frame_5)
        self.cancel_pushButton.setObjectName("cancel_pushButton")
    
        spacerItem2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        
        self.delpip_pushButton = QtWidgets.QPushButton(self.frame_5)
        self.delpip_pushButton.setObjectName("delpip_pushButton")        
        self.save_pushButton = QtWidgets.QPushButton(self.frame_5)
        self.save_pushButton.setObjectName("pushButton")

        self.horizontalLayout.addWidget(self.delpip_pushButton)
        self.horizontalLayout.addItem(spacerItem2)
        self.horizontalLayout.addWidget(self.cancel_pushButton)
        self.horizontalLayout.addWidget(self.save_pushButton)
        self.gridLayout_2.addWidget(self.frame_5, 5, 0, 1, 2)

        self.frame = QtWidgets.QFrame(self.mframe)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label_4 = QtWidgets.QLabel(self.frame)
        font = QtGui.QFont()
        font.setFamily("DejaVu Serif Condensed")
        font.setPointSize(30)
        self.label_4.setFont(font)
        self.label_4.setTextFormat(QtCore.Qt.AutoText)
        self.label_4.setAlignment(QtCore.Qt.AlignCenter)
        self.label_4.setObjectName("label_4")
        self.verticalLayout.addWidget(self.label_4)
        self.gridLayout_2.addWidget(self.frame, 0, 0, 1, 2)

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)
        self.init_pipeline_comboBox()
        self.init_analysis_comboBox()
        self.init_variables()
        self.init_treewidget_checkstate()
        self.init_ref_comboBox()
        self.show()

    def getToolscfg(self):
        tool_options = QFileDialog.Options()
        tool_options |= QFileDialog.DontUseNativeDialog
        starting_folder = self.configs_folder
        file, _ = QFileDialog.getOpenFileName(self,"Choose Tools configuration file", starting_folder,"Tools configuration files (*.cfg *.cfg.json)", options=tool_options)
        if file:
            self.tools_cfg_lineEdit.setText(file)
            self.tools_cfg = json.loads((open(file).read()).encode('utf8'))
            
    def init_functions(self):
        self.treeWidget.itemClicked.connect(self.onTreeItemClicked)
        self.treeWidget.itemChanged.connect(self.onTreeItemActivated)
        self.tool_listWidget.itemClicked.connect(self.onToolItemClicked)        
        self.tool_tableWidget.itemChanged.connect(self.tool_info_change)
        self.tool_tableWidget.doubleClicked.connect(self.onToolItemDoubleClicked)
        self.pipeline_comboBox.textActivated.connect(self.on_pipeline_combobox_changed)
        self.tools_toolButton.clicked.connect(self.getToolscfg)
        self.step_tableWidget.itemChanged.connect(self.step_info_change)
        self.useTool_pushButton.clicked.connect(self.add_tool)
        self.removeTool_pushButton.clicked.connect(self.remove_tool)
        self.ref_comboBox.currentTextChanged.connect(self.on_ref_combobox_changed)
        self.analysis_comboBox.currentTextChanged.connect(self.on_analysis_combobox_changed)
        self.save_pushButton.clicked.connect(self.save_pipeline)
        self.cancel_pushButton.clicked.connect(self.cancel_pipeline)
        self.delpip_pushButton.clicked.connect(self.delete_pipeline)

    def init_ref_comboBox(self):
        self.ref_comboBox.clear()
        for ref in self.tools_cfg["refGenomes_list"]:
            self.ref_comboBox.addItem(ref)
        try:
            i = self.ref_comboBox.findText(self.new_pipeline['reference_version'])
            self.ref_comboBox.setCurrentIndex(i)
        except:
            pass

    def init_pipeline_comboBox(self):
        self.pipeline_comboBox.clear()
        self.configs_folder = '/'.join(os.path.dirname(os.path.realpath(__file__)).split('/')[:-1] + ['configs'])
        starting_folder = self.configs_folder + '/pipelines/'
        pipeline_list = glob.glob(starting_folder + "*.pipeline")
        self.pipeline_comboBox.addItem('-')
        for p in pipeline_list:
            self.pipeline_comboBox.addItem(p.split(starting_folder)[1].split('.pipeline')[0])
            self.new_pipeline = json.loads((open(starting_folder+'/default.pipeline').read()).encode('utf8'))

    def init_analysis_comboBox(self):
        self.analysis_comboBox.clear()
        self.analysis_comboBox.addItem('Germline')
        self.analysis_comboBox.addItem('Somatic')
        self.analysis_comboBox.addItem('cfDNA')
        #print(self.new_pipeline['analysis'])
        i = self.analysis_comboBox.findText(self.new_pipeline['analysis'])
        self.analysis_comboBox.setCurrentIndex(i)

    def init_treewidget_checkstate(self):
        
        STEP_workflow = self.new_pipeline["workflow"]
        #print(self.new_pipeline)

        if 'variantcalling' in STEP_workflow:
            self.treeWidget.topLevelItem(3).child(0).setCheckState(0,2)
            self.treeWidget.topLevelItem(3).child(0).setText(1,','.join(self.new_pipeline["variantcalling"]["tools"]))
        else:
            self.treeWidget.topLevelItem(3).child(0).setCheckState(0,0)
            self.treeWidget.topLevelItem(3).child(0).setText(1,','.join(self.new_pipeline["variantcalling"]["tools"]))

        if 'cnvcalling' in STEP_workflow:
            self.treeWidget.topLevelItem(3).child(1).setCheckState(0,2)
            self.treeWidget.topLevelItem(3).child(1).setText(1,','.join(self.new_pipeline["cnvcalling"]["tools"])) 
        else:
            self.treeWidget.topLevelItem(3).child(1).setCheckState(0,0)
            self.treeWidget.topLevelItem(3).child(1).setText(1,','.join(self.new_pipeline["cnvcalling"]["tools"]))

        if 'variant_annotation' in STEP_workflow:
            self.treeWidget.topLevelItem(5).child(0).setCheckState(0,2)
            self.treeWidget.topLevelItem(5).child(0).setText(1,self.new_pipeline["variant_annotation"]["tool"])
        else:
            self.treeWidget.topLevelItem(5).child(0).setCheckState(0,0)
            self.treeWidget.topLevelItem(5).child(0).setText(1,self.new_pipeline["variant_annotation"]["tool"])

        if 'cnv_annotation' in STEP_workflow:
            self.treeWidget.topLevelItem(5).child(1).setCheckState(0,2)
            self.treeWidget.topLevelItem(5).child(1).setText(1,self.new_pipeline["cnv_annotation"]["tool"])
        else:
            self.treeWidget.topLevelItem(5).child(1).setCheckState(0,0)
            self.treeWidget.topLevelItem(5).child(1).setText(1,self.new_pipeline["cnv_annotation"]["tool"])

        if 'prealignment' not in STEP_workflow:
            self.treeWidget.topLevelItem(0).setCheckState(0,0)

        if 'alignment' not in STEP_workflow:
            self.treeWidget.topLevelItem(1).setCheckState(0,0)

        if 'preprocessing' not in STEP_workflow:
            self.treeWidget.topLevelItem(2).setCheckState(0,0)

        if 'postprocessing' not in STEP_workflow:
            self.treeWidget.topLevelItem(4).setCheckState(0,0)

        if 'postannotation' not in STEP_workflow:
            self.treeWidget.topLevelItem(6).setCheckState(0,0)
            
        for STEP in STEP_workflow:

            try:
                step_workflow = self.new_pipeline[STEP]["workflow"]
                #print(STEP,step_workflow)
                if STEP == 'prealignment':

                    if "trim_adapters" in step_workflow:
                        self.treeWidget.topLevelItem(0).child(0).setCheckState(0,2)
                        self.treeWidget.topLevelItem(0).child(0).setText(1,self.new_pipeline["prealignment"]["trim_adapters"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(0).child(0).setCheckState(0,0)
                        self.treeWidget.topLevelItem(0).child(0).setText(1,self.new_pipeline["prealignment"]["trim_adapters"]["tool"])
                    if  "filter_fastq_by_len" in step_workflow:
                        self.treeWidget.topLevelItem(0).child(1).setCheckState(0,2)
                        self.treeWidget.topLevelItem(0).child(1).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_len"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(0).child(1).setCheckState(0,0)
                        self.treeWidget.topLevelItem(0).child(1).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_len"]["tool"])
                    if "filter_fastq_by_qual" in step_workflow:
                        self.treeWidget.topLevelItem(0).child(2).setCheckState(0,2)
                        self.treeWidget.topLevelItem(0).child(2).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_qual"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(0).child(2).setCheckState(0,0)
                        self.treeWidget.topLevelItem(0).child(2).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_qual"]["tool"])
                    if "fastq_QC" in step_workflow:
                        self.treeWidget.topLevelItem(0).child(3).setCheckState(0,2)
                        self.treeWidget.topLevelItem(0).child(3).setText(1,self.new_pipeline["prealignment"]["fastq_QC"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(0).child(3).setCheckState(0,0)
                        self.treeWidget.topLevelItem(0).child(3).setText(1,self.new_pipeline["prealignment"]["fastq_QC"]["tool"])

                if STEP == 'alignment':
                    if "merge_UMI" in step_workflow:
                        self.treeWidget.topLevelItem(1).child(0).setCheckState(0,2)
                        self.treeWidget.topLevelItem(1).child(0).setText(1,self.new_pipeline["alignment"]["merge_UMI"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(1).child(0).setCheckState(0,0)
                        self.treeWidget.topLevelItem(1).child(0).setText(1,self.new_pipeline["alignment"]["merge_UMI"]["tool"])
                    if "fastq_alignment" in step_workflow:
                        self.treeWidget.topLevelItem(1).child(1).setCheckState(0,2)
                        self.treeWidget.topLevelItem(1).child(1).setText(1,self.new_pipeline["alignment"]["fastq_alignment"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(1).child(1).setCheckState(0,0)
                        self.treeWidget.topLevelItem(1).child(1).setText(1,self.new_pipeline["alignment"]["fastq_alignment"]["tool"])
                    if "sam_to_bam" in step_workflow:
                        self.treeWidget.topLevelItem(1).child(2).setCheckState(0,2)
                        self.treeWidget.topLevelItem(1).child(2).setText(1,self.new_pipeline["alignment"]["sam_to_bam"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(1).child(2).setCheckState(0,0)
                        self.treeWidget.topLevelItem(1).child(2).setText(1,self.new_pipeline["alignment"]["sam_to_bam"]["tool"])
                    if "sortSam" in step_workflow:
                        self.treeWidget.topLevelItem(1).child(3).setCheckState(0,2)
                        self.treeWidget.topLevelItem(1).child(3).setText(1,self.new_pipeline["alignment"]["sortSam"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(1).child(3).setCheckState(0,0)
                        self.treeWidget.topLevelItem(1).child(3).setText(1,self.new_pipeline["alignment"]["sortSam"]["tool"])
                    if "bam_QC" in step_workflow:
                        self.treeWidget.topLevelItem(1).child(4).setCheckState(0,2)
                        self.treeWidget.topLevelItem(1).child(4).setText(1,self.new_pipeline["alignment"]["bam_QC"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(1).child(4).setCheckState(0,0)
                        self.treeWidget.topLevelItem(1).child(4).setText(1,self.new_pipeline["alignment"]["bam_QC"]["tool"])


                if STEP == 'preprocessing':
                    if "filter_bam" in step_workflow:
                        self.treeWidget.topLevelItem(2).child(0).setCheckState(0,2)
                        self.treeWidget.topLevelItem(2).child(0).setText(1,self.new_pipeline["preprocessing"]["filter_bam"]["tool"])
                    else:
                        self.treeWidget.topLevelItem(2).child(0).setCheckState(0,0)
                        self.treeWidget.topLevelItem(2).child(0).setText(1,self.new_pipeline["preprocessing"]["filter_bam"]["tool"])
                    if "add_readgroups" in step_workflow:
                        self.treeWidget.topLevelItem(2).child(1).setCheckState(0,2)
                        self.treeWidget.topLevelItem(2).child(1).setText(1,self.new_pipeline["preprocessing"]["add_readgroups"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(2).child(1).setCheckState(0,0)
                        self.treeWidget.topLevelItem(2).child(1).setText(1,self.new_pipeline["preprocessing"]["add_readgroups"]["tool"])
                    if "mark_pcr_dup" in step_workflow:
                        self.treeWidget.topLevelItem(2).child(2).setCheckState(0,2)
                        self.treeWidget.topLevelItem(2).child(2).setText(1,self.new_pipeline["preprocessing"]["mark_pcr_dup"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(2).child(2).setCheckState(0,0)
                        self.treeWidget.topLevelItem(2).child(2).setText(1,self.new_pipeline["preprocessing"]["mark_pcr_dup"]["tool"])
                    if "indel_realignment" in step_workflow:
                        self.treeWidget.topLevelItem(2).child(3).setCheckState(0,2)
                        self.treeWidget.topLevelItem(2).child(3).setText(1,self.new_pipeline["preprocessing"]["indel_realignment"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(2).child(3).setCheckState(0,0)
                        self.treeWidget.topLevelItem(2).child(3).setText(1,self.new_pipeline["preprocessing"]["indel_realignment"]["tool"])
                    if "BQ_recalibration" in step_workflow:
                        self.treeWidget.topLevelItem(2).child(4).setCheckState(0,2)
                        self.treeWidget.topLevelItem(2).child(4).setText(1,self.new_pipeline["preprocessing"]["BQ_recalibration"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(2).child(4).setCheckState(0,0)
                        self.treeWidget.topLevelItem(2).child(4).setText(1,self.new_pipeline["preprocessing"]["BQ_recalibration"]["tool"])


                if STEP == 'postprocessing':
                    #print(self.new_pipeline[STEP])
                    if "vcf_filter" in step_workflow:
                        self.treeWidget.topLevelItem(4).child(0).setCheckState(0,2)
                        self.treeWidget.topLevelItem(4).child(0).setText(1,self.new_pipeline["postprocessing"]["vcf_filter"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(4).child(0).setCheckState(0,0)
                        self.treeWidget.topLevelItem(4).child(0).setText(1,self.new_pipeline["postprocessing"]["vcf_filter"]["tool"])
                    
                    if "vcf_norm" in step_workflow:
                        self.treeWidget.topLevelItem(4).child(1).setCheckState(0,2)
                        self.treeWidget.topLevelItem(4).child(1).setText(1,self.new_pipeline["postprocessing"]["vcf_norm"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(4).child(1).setCheckState(0,0)
                        self.treeWidget.topLevelItem(4).child(1).setText(1,self.new_pipeline["postprocessing"]["vcf_norm"]["tool"])
                #elif step == "Hard filter":
                    #self.treeWidget.topLevelItem(4).child(2).setCheckState(0,2)
                    if "vcf_to_tsv" in step_workflow:
                        self.treeWidget.topLevelItem(4).child(2).setCheckState(0,2)
                        self.treeWidget.topLevelItem(4).child(2).setText(1,self.new_pipeline["postprocessing"]["vcf_to_tsv"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(4).child(2).setCheckState(0,0)
                        self.treeWidget.topLevelItem(4).child(2).setText(1,self.new_pipeline["postprocessing"]["vcf_to_tsv"]["tool"])

                if STEP == 'postannotation':       
                    if "ann_filter" in step_workflow:
                        self.treeWidget.topLevelItem(6).child(0).setCheckState(0,2)
                        self.treeWidget.topLevelItem(6).child(0).setText(1,self.new_pipeline["postannotation"]["ann_filter"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(6).child(0).setCheckState(0,0)
                        self.treeWidget.topLevelItem(6).child(0).setText(1,self.new_pipeline["postannotation"]["ann_filter"]["tool"])
                    if "filter_by_trs_list" in step_workflow:
                        self.treeWidget.topLevelItem(6).child(1).setCheckState(0,2)
                        self.treeWidget.topLevelItem(6).child(1).setText(1,self.new_pipeline["postannotation"]["filter_by_trs_list"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(6).child(1).setCheckState(0,0)
                        self.treeWidget.topLevelItem(6).child(1).setText(1,self.new_pipeline["postannotation"]["filter_by_trs_list"]["tool"])
                    if "ann_vcf_to_tsv" in step_workflow:
                        self.treeWidget.topLevelItem(6).child(2).setCheckState(0,2)
                        self.treeWidget.topLevelItem(6).child(2).setText(1,self.new_pipeline["postannotation"]["ann_vcf_to_tsv"]["tool"])
                    else: 
                        self.treeWidget.topLevelItem(6).child(2).setCheckState(0,0)
                        self.treeWidget.topLevelItem(6).child(2).setText(1,self.new_pipeline["postannotation"]["ann_vcf_to_tsv"]["tool"])

            except Exception as e:
                print(e)               
                 
    def init_treewidget_tool(self):
        self.treeWidget.topLevelItem(0).child(0).setText(1,self.new_pipeline["prealignment"]["trim_adapters"]["tool"])
        self.treeWidget.topLevelItem(0).child(1).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_len"]["tool"])
        self.treeWidget.topLevelItem(0).child(2).setText(1,self.new_pipeline["prealignment"]["filter_fastq_by_qual"]["tool"])
        self.treeWidget.topLevelItem(0).child(3).setText(1,self.new_pipeline["prealignment"]["fastq_QC"]["tool"])
        #self.treeWidget.topLevelItem(1).child(0).setText(1,self.new_pipeline["alignment"]["merge_UMI"]["tool"])
        self.treeWidget.topLevelItem(1).child(1).setText(1,self.new_pipeline["alignment"]["fastq_alignment"]["tool"])
        self.treeWidget.topLevelItem(1).child(2).setText(1,self.new_pipeline["alignment"]["sam_to_bam"]["tool"])
        self.treeWidget.topLevelItem(1).child(3).setText(1,self.new_pipeline["alignment"]["sortSam"]["tool"])
        self.treeWidget.topLevelItem(1).child(4).setText(1,self.new_pipeline["alignment"]["bam_QC"]["tool"])
        self.treeWidget.topLevelItem(2).child(0).setText(1,self.new_pipeline["preprocessing"]["filter_bam"]["tool"])
        self.treeWidget.topLevelItem(2).child(1).setText(1,self.new_pipeline["preprocessing"]["add_readgroups"]["tool"])
        self.treeWidget.topLevelItem(2).child(2).setText(1,self.new_pipeline["preprocessing"]["mark_pcr_dup"]["tool"])
        self.treeWidget.topLevelItem(2).child(3).setText(1,self.new_pipeline["preprocessing"]["indel_realignment"]["tool"])
        self.treeWidget.topLevelItem(2).child(4).setText(1,self.new_pipeline["preprocessing"]["BQ_recalibration"]["tool"])
        self.treeWidget.topLevelItem(3).child(0).setText(1,','.join(self.new_pipeline["variantcalling"]["tools"]))
        self.treeWidget.topLevelItem(3).child(1).setText(1,','.join(self.new_pipeline["cnvcalling"]["tools"])) 
        
        self.treeWidget.topLevelItem(4).child(0).setText(1,self.new_pipeline["postprocessing"]["vcf_filter"]["tool"])
        self.treeWidget.topLevelItem(4).child(1).setText(1,self.new_pipeline["postprocessing"]["vcf_norm"]["tool"])
        self.treeWidget.topLevelItem(4).child(2).setText(1,self.new_pipeline["postprocessing"]["vcf_to_tsv"]["tool"])
        self.treeWidget.topLevelItem(5).child(0).setText(1,self.new_pipeline["variant_annotation"]["tool"])
        self.treeWidget.topLevelItem(5).child(1).setText(1,self.new_pipeline["cnv_annotation"]["tool"])
        self.treeWidget.topLevelItem(6).child(0).setText(1,self.new_pipeline["postannotation"]["ann_filter"]["tool"])
        self.treeWidget.topLevelItem(6).child(1).setText(1,self.new_pipeline["postannotation"]["filter_by_trs_list"]["tool"])
        self.treeWidget.topLevelItem(6).child(2).setText(1,self.new_pipeline["postannotation"]["ann_vcf_to_tsv"]["tool"])

    def init_variables(self):
        config_default = self.configs_folder + '/panels_cfg/Tools_test.cfg'
        self.tools_cfg_lineEdit.setText(config_default)
        self.tools_cfg = json.loads((open(config_default).read()).encode('utf8'))
        self.init_ref_comboBox()
        self.STEP = None
        self.old_pipeline_name = self.pipeline_comboBox.currentText()
        self.old_pipeline_index = self.pipeline_comboBox.currentIndex()
        self.dict_steps = {
            "Pre-Alignment":{"STEP":"prealignment","step":"prealignment"},
            "Adapters trimming":{"STEP":"prealignment","step":"trim_adapters"},
            "FASTQ read lenght filter":{"STEP":"prealignment","step":"filter_fastq_by_len"},
            "FASTQ quality filter":{"STEP":"prealignment","step":"filter_fastq_by_qual"},
            "FASTQ quality control":{"STEP":"prealignment","step":"fastq_QC"},
            "Alignment":{"STEP":"alignment","step":"alignment"},
            "UMI/Molecular barcodes merge":{"STEP":"alignment","step":"merge_UMI"},
            "FASTQ alignment":{"STEP":"alignment","step":"fastq_alignment"},
            "SAM to BAM convertion":{"STEP":"alignment","step":"sam_to_bam"},
            "BAM sort":{"STEP":"alignment","step":"sortSam"},
            "BAM quality control":{"STEP":"alignment","step":"bam_QC"},
            "Pre-Processing":{"STEP":"preprocessing","step":"preprocessing"},
            "BAM filter":{"STEP":"preprocessing","step":"filter_bam"},
            "Add readgroups to BAM":{"STEP":"preprocessing","step":"add_readgroups"},
            "PCR duplicates marking":{"STEP":"preprocessing","step":"mark_pcr_dup"},
            "InDels realignment":{"STEP":"preprocessing","step":"indel_realignment"},
            "Base quality recalibration":{"STEP":"preprocessing","step":"BQ_recalibration"},
            "VC SNV & short InDels":{"STEP":"variantcalling","step":"variantcalling"},
            "VC Copy Number Variation":{"STEP":"cnvcalling","step":"cnvcalling"},
            "Post-Processing":{"STEP":"postprocessing","step":"postprocessing"},
            "VCF filter":{"STEP":"postprocessing","step":"vcf_filter"},
            "VCF normalization":{"STEP":"postprocessing","step":"vcf_norm"},
            "VCF to TSV convertion":{"STEP":"postprocessing","step":"vcf_to_tsv"},
            "Ann SNV & short InDels":{"STEP":"variant_annotation","step":"variant_annotation"},
            "Ann Copy Number Variation":{"STEP":"cnv_annotation","step":"cnv_annotation"},
            "Post-Annotation":{"STEP":"postannotation","step":"postannotation"},
            "Annotation filter":{"STEP":"postannotation","step":"ann_filter"},
            "Annotated VCF to TSV convertion":{"STEP":"postannotation","step":"ann_vcf_to_tsv"},
            "Ann transcripts filter":{"STEP":"postannotation","step":"filter_by_trs_list"}
            }
        #self.new_pipeline = None

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("Pipeline_designer", "Pipeline designer"))
        self.label.setText(_translate("Pipeline_designer", "-"))
        self.tool_listWidget.setSortingEnabled(True)
        __sortingEnabled = self.tool_listWidget.isSortingEnabled()
        self.tool_listWidget.setSortingEnabled(False)
        self.tool_listWidget.setSortingEnabled(__sortingEnabled)
        self.label_4.setText(_translate("Pipeline_page", "Pipeline Designer"))
        self.save_pushButton.setText(_translate("Pipeline_designer", "Save"))
        self.ref_label.setText(_translate("Pipeline_designer", "Reference version:"))
        self.tools_label.setText(_translate("Pipeline_designer", "Tools cfg:"))
        self.tools_toolButton.setText(_translate("Pipeline_designer", "..."))
        self.Pipeline_name.setText(_translate("Pipeline_designer", "Pipeline:"))
        self.analysis_label.setText(_translate("Pipeline_designer", "Analysis:"))
        self.cancel_pushButton.setText(_translate("Pipeline_designer", "Cancel"))
        
        self.delpip_pushButton.setText(_translate("Pipeline_designer", "Delete Pipeline"))
        self.treeWidget.headerItem().setText(0, _translate("Pipeline_designer", "Analysis Steps"))
        self.treeWidget.headerItem().setText(1, _translate("Pipeline_designer", "Tools"))
        __sortingEnabled = self.treeWidget.isSortingEnabled()
        self.treeWidget.setSortingEnabled(False)
        self.treeWidget.topLevelItem(0).setText(0, _translate("Pipeline_designer", "Pre-Alignment"))
        self.treeWidget.topLevelItem(0).child(0).setText(0, _translate("Pipeline_designer", "Adapters trimming"))
        self.treeWidget.topLevelItem(0).child(1).setText(0, _translate("Pipeline_designer", "FASTQ read lenght filter"))
        self.treeWidget.topLevelItem(0).child(2).setText(0, _translate("Pipeline_designer", "FASTQ quality filter"))
        self.treeWidget.topLevelItem(0).child(3).setText(0, _translate("Pipeline_designer", "FASTQ quality control"))
        self.treeWidget.topLevelItem(1).setText(0, _translate("Pipeline_designer", "Alignment"))
        self.treeWidget.topLevelItem(1).child(0).setText(0, _translate("Pipeline_designer", "UMI/Molecular barcodes merge"))
        self.treeWidget.topLevelItem(1).child(1).setText(0, _translate("Pipeline_designer", "FASTQ alignment"))
        self.treeWidget.topLevelItem(1).child(2).setText(0, _translate("Pipeline_designer", "SAM to BAM convertion"))
        self.treeWidget.topLevelItem(1).child(3).setText(0, _translate("Pipeline_designer", "BAM sort"))
        self.treeWidget.topLevelItem(1).child(4).setText(0, _translate("Pipeline_designer", "BAM quality control"))
        self.treeWidget.topLevelItem(2).setText(0, _translate("Pipeline_designer", "Pre-Processing"))
        self.treeWidget.topLevelItem(2).child(0).setText(0, _translate("Pipeline_designer", "BAM filter"))
        self.treeWidget.topLevelItem(2).child(1).setText(0, _translate("Pipeline_designer", "Add readgroups to BAM"))
        self.treeWidget.topLevelItem(2).child(2).setText(0, _translate("Pipeline_designer", "PCR duplicates marking"))
        self.treeWidget.topLevelItem(2).child(3).setText(0, _translate("Pipeline_designer", "InDels realignment"))
        self.treeWidget.topLevelItem(2).child(4).setText(0, _translate("Pipeline_designer", "Base quality recalibration"))
        self.treeWidget.topLevelItem(3).setText(0, _translate("Pipeline_designer", "Variant Calling"))
        self.treeWidget.topLevelItem(3).child(0).setText(0, _translate("Pipeline_designer", "VC SNV & short InDels"))
        self.treeWidget.topLevelItem(3).child(1).setText(0, _translate("Pipeline_designer", "VC Copy Number Variation"))
        self.treeWidget.topLevelItem(4).setText(0, _translate("Pipeline_designer", "Post-Processing"))
        self.treeWidget.topLevelItem(4).child(0).setText(0, _translate("Pipeline_designer", "VCF filter"))
        self.treeWidget.topLevelItem(4).child(1).setText(0, _translate("Pipeline_designer", "VCF normalization"))
        #self.treeWidget.topLevelItem(4).child(1).setText(0, _translate("Pipeline_designer", "Hard filter"))
        self.treeWidget.topLevelItem(4).child(2).setText(0, _translate("Pipeline_designer", "VCF to TSV convertion"))
        self.treeWidget.topLevelItem(5).setText(0, _translate("Pipeline_designer", "Annotation"))
        self.treeWidget.topLevelItem(5).child(0).setText(0, _translate("Pipeline_designer", "Ann SNV & short InDels"))
        self.treeWidget.topLevelItem(5).child(1).setText(0, _translate("Pipeline_designer", "Ann Copy Number Variation"))
        self.treeWidget.topLevelItem(6).setText(0, _translate("Pipeline_designer", "Post-Annotation"))
        self.treeWidget.topLevelItem(6).child(0).setText(0, _translate("Pipeline_designer", "Annotation filter"))
        self.treeWidget.topLevelItem(6).child(2).setText(0, _translate("Pipeline_designer", "Annotated VCF to TSV convertion"))
        self.treeWidget.topLevelItem(6).child(1).setText(0, _translate("Pipeline_designer", "Ann transcripts filter"))
        self.useTool_pushButton.setText(_translate("Pipeline_page", "Use/add this tool"))
        self.removeTool_pushButton.setText(_translate("Pipeline_page", "Don\'t use this tool"))
        self.treeWidget.setSortingEnabled(__sortingEnabled)

