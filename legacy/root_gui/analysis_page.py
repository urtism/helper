from PyQt5 import QtCore, QtGui, QtWidgets
import sheet_compiler as sc
import samplesheet_designer as ssd
import analysis_page as ap
import Experiment_builder as eb
import tool_settings as ts
import pipeline_designer as pd
import os.path
import subprocess
import json
import glob


class Analysis_page(QtWidgets.QWidget):

    def __init__(self, parent = None):
        super(Analysis_page, self).__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("Analysis_page")
        self.resize(935, 869)
        self.gridLayout_2 = QtWidgets.QGridLayout(self)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.frame_2 = QtWidgets.QFrame(self)
        self.frame_2.setMaximumSize(QtCore.QSize(16777215, 101))
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame_2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.start_analysis_pushButton = QtWidgets.QPushButton(self.frame_2)
        self.start_analysis_pushButton.setMinimumSize(QtCore.QSize(0, 51))
        self.start_analysis_pushButton.setMaximumSize(QtCore.QSize(16777215, 71))
        self.start_analysis_pushButton.setObjectName("pushButton")
        self.verticalLayout.addWidget(self.start_analysis_pushButton)
        self.gridLayout_2.addWidget(self.frame_2, 4, 0, 1, 1)
        self.frame_3 = QtWidgets.QFrame(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy)
        self.frame_3.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.frame_3)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label_10 = QtWidgets.QLabel(self.frame_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_10.sizePolicy().hasHeightForWidth())
        self.label_10.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily("DejaVu Serif Condensed")
        font.setPointSize(30)
        self.label_10.setFont(font)
        self.label_10.setTextFormat(QtCore.Qt.AutoText)
        self.label_10.setAlignment(QtCore.Qt.AlignCenter)
        self.label_10.setObjectName("label_10")
        self.verticalLayout_3.addWidget(self.label_10)
        self.gridLayout_2.addWidget(self.frame_3, 0, 0, 1, 1)
        self.frame = QtWidgets.QFrame(self)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.frame)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.frame_21 = QtWidgets.QFrame(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_21.sizePolicy().hasHeightForWidth())
        self.frame_21.setSizePolicy(sizePolicy)
        self.frame_21.setObjectName("frame_21")
        self.formLayout_2 = QtWidgets.QFormLayout(self.frame_21)
        self.formLayout_2.setObjectName("formLayout_2")
        self.treeWidget = QtWidgets.QTreeWidget(self.frame_21)
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
        self.treeWidget.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.treeWidget.setFrameShadow(QtWidgets.QFrame.Plain)
        self.treeWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.treeWidget.setTextElideMode(QtCore.Qt.ElideRight)
        self.treeWidget.setAutoExpandDelay(-1)
        self.treeWidget.setIndentation(20)
        self.treeWidget.setRootIsDecorated(True)
        self.treeWidget.setAnimated(True)
        self.treeWidget.setAllColumnsShowFocus(False)
        self.treeWidget.setHeaderHidden(False)
        self.treeWidget.setColumnCount(1)
        self.treeWidget.setObjectName("treeWidget")
        self.item_pre_alig = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_pre_alig.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_pre_alig.flags())
        self.item_adapt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_adapt.setFlags(self.item_adapt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_adapt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_len_filt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_len_filt.setFlags(self.item_len_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_len_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_q_filt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_q_filt.setFlags(self.item_q_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_q_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_fq_qc = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_fq_qc.setFlags(self.item_fq_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_fq_qc.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_align = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_align.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_align.flags())      
        self.item_alig = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_alig.setFlags(self.item_alig.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_alig.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_sambam = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_sambam.setFlags(self.item_sambam.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_sambam.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_umi = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_umi.setFlags(self.item_umi.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_umi.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_sort = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_sort.setFlags(self.item_sort.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_sort.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_bam_qc = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_bam_qc.setFlags(self.item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bam_qc.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_pre_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_pre_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_pre_proc.flags())      
       
        self.item_bam_filt = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_bam_filt.setFlags(self.item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bam_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_rgroup = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_rgroup.setFlags(self.item_rgroup.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_rgroup.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_dup = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_dup.setFlags(self.item_dup.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_dup.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_realig = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_realig.setFlags(self.item_realig.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_realig.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_bqsr = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_bqsr.setFlags(self.item_bqsr.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bqsr.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_vcalling = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_vcalling.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_vcalling.flags())      
    
        self.item_shortv_call = QtWidgets.QTreeWidgetItem(self.item_vcalling)
        self.item_shortv_call.setFlags(self.item_shortv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_shortv_call.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_cnv_call = QtWidgets.QTreeWidgetItem(self.item_vcalling)
        self.item_cnv_call.setFlags(self.item_cnv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_cnv_call.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_post_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_post_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_post_proc.flags())      
    
        self.item_vcf_norm = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_norm.setFlags(self.item_vcf_norm.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_norm.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_filt = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_filt.setFlags(self.item_vcf_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_to_tsv = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_to_tsv.setFlags(self.item_vcf_to_tsv.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_ann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_ann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_ann.flags())      
    
        self.item_shortv_ann = QtWidgets.QTreeWidgetItem(self.item_ann)
        self.item_shortv_ann.setFlags(self.item_shortv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_shortv_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_cnv_ann = QtWidgets.QTreeWidgetItem(self.item_ann)
        self.item_cnv_ann.setFlags(self.item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_cnv_ann.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_postann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_postann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_postann.flags())      
        
        self.item_filt_ann = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_filt_ann.setFlags(self.item_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_trs_filt_ann = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_trs_filt_ann.setFlags(self.item_trs_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_trs_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_ann_to_tsv = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_vcf_ann_to_tsv.setFlags(self.item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_ann_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)
        self.treeWidget.header().setVisible(True)
        self.treeWidget.header().setCascadingSectionResizes(True)
        self.treeWidget.header().setDefaultSectionSize(296)
        self.treeWidget.header().setHighlightSections(False)
        self.treeWidget.header().setMinimumSectionSize(100)
        self.treeWidget.header().setSortIndicatorShown(False)
        self.treeWidget.header().setStretchLastSection(True)
        self.formLayout_2.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.treeWidget)
        self.paral_checkBox = QtWidgets.QCheckBox(self.frame_21)
        self.paral_checkBox.setObjectName("paral_checkBox")
        self.formLayout_2.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.paral_checkBox)
        self.del_temp_checkBox = QtWidgets.QCheckBox(self.frame_21)
        self.del_temp_checkBox.setObjectName("del_temp_checkBox")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.del_temp_checkBox)
        self.gridLayout_3.addWidget(self.frame_21, 0, 1, 2, 1)
        self.frame_5 = QtWidgets.QFrame(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_5.sizePolicy().hasHeightForWidth())
        self.frame_5.setSizePolicy(sizePolicy)
        self.frame_5.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.frame_5.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_5.setObjectName("frame_5")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.frame_5)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.groupBox = QtWidgets.QGroupBox(self.frame_5)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy)
        self.groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox.setObjectName("groupBox")
        self.formLayout = QtWidgets.QFormLayout(self.groupBox)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.runID_lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.runID_lineEdit.setObjectName("lineEdit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.runID_lineEdit)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.panels_comboBox = QtWidgets.QComboBox(self.groupBox)
        self.panels_comboBox.setObjectName("comboBox")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole,  self.panels_comboBox)
        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.pipeline_comboBox = QtWidgets.QComboBox(self.groupBox)
        self.pipeline_comboBox.setObjectName("pipeline_comboBox")
        self.pipeline_comboBox.addItem("")
        self.pipeline_comboBox.addItem("")
        self.pipeline_comboBox.addItem("")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.pipeline_comboBox)
        self.verticalLayout_4.addWidget(self.groupBox)
        self.groupBox_3 = QtWidgets.QGroupBox(self.frame_5)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_3.sizePolicy().hasHeightForWidth())
        self.groupBox_3.setSizePolicy(sizePolicy)
        self.groupBox_3.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_3)
        self.gridLayout.setObjectName("gridLayout")
        self.workdir_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.workdir_toolButton.setObjectName("workdir_toolButton")
        self.gridLayout.addWidget(self.workdir_toolButton, 2, 2, 1, 1)
        self.tools_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.tools_toolButton.setObjectName("tools_toolButton")
        self.gridLayout.addWidget(self.tools_toolButton, 3, 2, 1, 1)
        self.label_6 = QtWidgets.QLabel(self.groupBox_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_6.sizePolicy().hasHeightForWidth())
        self.label_6.setSizePolicy(sizePolicy)
        self.label_6.setObjectName("label_6")
        self.gridLayout.addWidget(self.label_6, 3, 0, 1, 1)
        self.label_5 = QtWidgets.QLabel(self.groupBox_3)
        self.label_5.setObjectName("label_5")
        self.gridLayout.addWidget(self.label_5, 2, 0, 1, 1)
        self.samplesheet_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.samplesheet_toolButton.setObjectName("toolButton")
        self.gridLayout.addWidget(self.samplesheet_toolButton, 1, 2, 1, 1)
        self.workDir_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.workDir_lineEdit.setObjectName("workDir_lineEdit")
        self.gridLayout.addWidget(self.workDir_lineEdit, 2, 1, 1, 1)
        self.label_4 = QtWidgets.QLabel(self.groupBox_3)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 0, 1, 1)
        self.samplesheet_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.samplesheet_lineEdit.setObjectName("samplesheet_lineEdit")
        self.gridLayout.addWidget(self.samplesheet_lineEdit, 1, 1, 1, 1)
        self.tools_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.tools_lineEdit.setObjectName("tools_lineEdit")
        self.gridLayout.addWidget(self.tools_lineEdit, 3, 1, 1, 1)
        self.verticalLayout_4.addWidget(self.groupBox_3)
        self.frame_4 = QtWidgets.QFrame(self.frame_5)
        self.frame_4.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.frame_4.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_4.setObjectName("frame_4")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.frame_4)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.label_7 = QtWidgets.QLabel(self.frame_4)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_7.setFont(font)
        self.label_7.setAlignment(QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft)
        self.label_7.setObjectName("label_7")
        self.verticalLayout_2.addWidget(self.label_7)
        self.analysis_list_QListWidget = QtWidgets.QListWidget(self.frame_4)
        self.analysis_list_QListWidget.setObjectName("textBrowser")
        self.verticalLayout_2.addWidget(self.analysis_list_QListWidget)
        self.frame_6 = QtWidgets.QFrame(self.frame_4)
        self.frame_6.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.frame_6.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_6.setObjectName("frame_6")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.frame_6)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.rem_queue_pushButton = QtWidgets.QPushButton(self.frame_6)
        self.rem_queue_pushButton.setObjectName("pushButton_3")
        self.horizontalLayout.addWidget(self.rem_queue_pushButton)
        self.add_queue_pushButton = QtWidgets.QPushButton(self.frame_6)
        self.add_queue_pushButton.setObjectName("pushButton_2")
        self.horizontalLayout.addWidget(self.add_queue_pushButton)
        self.verticalLayout_2.addWidget(self.frame_6)
        self.verticalLayout_4.addWidget(self.frame_4)
        self.gridLayout_3.addWidget(self.frame_5, 0, 0, 1, 1)
        self.gridLayout_2.addWidget(self.frame, 1, 0, 1, 1)
        self.init_functions()
        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)
        self.analysis_dict = {"analysis_list":[]}

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("Analysis_page", "Analysis Settings"))
        self.start_analysis_pushButton.setText(_translate("Analysis_page", "Start POWERCALL V2.0"))
        self.label_10.setText(_translate("Analysis_page", "Analysis Settings"))
        self.treeWidget.headerItem().setText(0, _translate("Analysis_page", "Analysis Steps"))
        __sortingEnabled = self.treeWidget.isSortingEnabled()
        self.treeWidget.setSortingEnabled(False)

        self.item_pre_alig.setText(0, _translate("Analysis_page", "Pre-Alignment"))
        self.item_adapt.setText(0, _translate("Analysis_page", "Adapters trimming"))
        self.item_len_filt.setText(0, _translate("Analysis_page", "FASTQ read lenght filter"))
        self.item_q_filt.setText(0, _translate("Analysis_page", "FASTQ quality filter"))
        self.item_fq_qc.setText(0, _translate("Analysis_page", "FASTQ quality control"))
        self.item_align.setText(0, _translate("Analysis_page", "Alignment"))
        self.item_umi.setText(0, _translate("Analysis_page", "UMI/Molecular barcodes merge"))
        self.item_alig.setText(0, _translate("Analysis_page", "FASTQ alignment"))
        self.item_sambam.setText(0, _translate("Analysis_page", "SAM to BAM convertion"))
        self.item_sort.setText(0, _translate("Analysis_page", "BAM sort"))
        self.item_bam_qc.setText(0, _translate("Analysis_page", "BAM quality control"))
        self.item_pre_proc.setText(0, _translate("Analysis_page", "Pre-Processing"))
        self.item_bam_filt.setText(0, _translate("Analysis_page", "BAM filter"))
        self.item_rgroup.setText(0, _translate("Analysis_page", "Add readgroups to BAM"))
        self.item_dup.setText(0, _translate("Analysis_page", "PCR duplicates marking"))
        self.item_realig.setText(0, _translate("Analysis_page", "InDels realignment"))
        self.item_bqsr.setText(0, _translate("Analysis_page", "Base quality recalibration"))
        self.item_vcalling.setText(0, _translate("Analysis_page", "Variant Calling"))
        self.item_shortv_call.setText(0, _translate("Analysis_page", "SNV & short InDels"))
        self.item_cnv_call.setText(0, _translate("Analysis_page", "Copy Number Variation"))
        self.item_post_proc.setText(0, _translate("Analysis_page", "Post-Processing"))
        self.item_vcf_filt.setText(0, _translate("Analysis_page", "VCF filter"))
        self.item_vcf_norm.setText(0, _translate("Analysis_page", "VCF normalization"))
        self.item_vcf_to_tsv.setText(0, _translate("Analysis_page", "VCF to TSV convertion"))
        self.item_ann.setText(0, _translate("Analysis_page", "Annotation"))
        self.item_shortv_ann.setText(0, _translate("Analysis_page", "SNV & short InDels"))
        self.item_cnv_ann.setText(0, _translate("Analysis_page", "Copy Number Variation"))
        self.item_postann.setText(0, _translate("Add_tags", "Post-Annotation"))
        self.item_filt_ann.setText(0, _translate("Analysis_page", "Annotation filter"))
        self.item_vcf_ann_to_tsv.setText(0, _translate("Analysis_page", "Annotated VCF to TSV convertion"))
        self.item_trs_filt_ann.setText(0, _translate("Analysis_page", "Ann transcripts filter"))
        self.treeWidget.setSortingEnabled(__sortingEnabled)
        self.paral_checkBox.setText(_translate("Analysis_page", "Use parallel analysis"))
        self.del_temp_checkBox.setText(_translate("Analysis_page", "Delete temp files"))
        self.groupBox.setTitle(_translate("Analysis_page", "Analysis Informations"))
        self.label.setText(_translate("Analysis_page", "Run ID"))
        self.label_2.setText(_translate("Analysis_page", "Panel Name"))
        # self.panels_comboBox.setItemText(0, _translate("Analysis_page", "Illumina TrusighCardio"))
        # self.panels_comboBox.setItemText(1, _translate("Analysis_page", "Illumina TrusighCancer"))
        # self.panels_comboBox.setItemText(2, _translate("Analysis_page", "Illumina TrusighOne"))
        # self.panels_comboBox.setItemText(3, _translate("Analysis_page", "SophiaGen HCS"))
        # self.panels_comboBox.setItemText(4, _translate("Analysis_page", "Agilent CardioV1"))
        # self.panels_comboBox.setItemText(5, _translate("Analysis_page", "Agilent AneurysmV1"))
        # self.panels_comboBox.setItemText(6, _translate("Analysis_page", "Agilent CancerV1"))
        self.label_3.setText(_translate("Analysis_page", "Pipeline"))
        # self.pipeline_comboBox.setItemText(0, _translate("Analysis_page", "Germline"))
        # self.pipeline_comboBox.setItemText(1, _translate("Analysis_page", "Somatic"))
        # self.pipeline_comboBox.setItemText(2, _translate("Analysis_page", "Cellfree"))
        self.groupBox_3.setTitle(_translate("Analysis_page", "Analysis Paths"))
        self.workdir_toolButton.setText(_translate("Analysis_page", "..."))
        self.tools_toolButton.setText(_translate("Analysis_page", "..."))
        self.label_6.setText(_translate("Analysis_page", "Tools config file"))
        self.label_5.setText(_translate("Analysis_page", "Working directory"))
        self.samplesheet_toolButton.setText(_translate("Analysis_page", "..."))
        self.label_4.setText(_translate("Analysis_page", "Samplesheet"))
        self.label_7.setText(_translate("Analysis_page", "Analysis Queue"))
        self.rem_queue_pushButton.setText(_translate("Analysis_page", "Remove"))
        self.add_queue_pushButton.setText(_translate("Analysis_page", "Add to Queue"))


    def init_pipeline_comboBox(self):
        self.pipeline_comboBox.clear()
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs/pipelines/'
        pipeline_list = glob.glob(starting_folder + "*.pipeline")
        self.pipeline_comboBox.addItem('-')
        for p in pipeline_list:
            self.pipeline_comboBox.addItem(p.split(starting_folder)[1].split('.pipeline')[0])

    def init_panels_combobox(self):
        self.panels_comboBox.clear()
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs/panels_cfg/'
        panles_list = glob.glob(starting_folder + "*.cfg")
        self.panels_comboBox.addItem('-')
        for p in panles_list:
            self.panels_comboBox.addItem(p.split(starting_folder)[1].split('.cfg')[0])



    def getsamplesheet(self):
        ss_options = QtWidgets.QFileDialog.Options()
        ss_options |= QtWidgets.QFileDialog.DontUseNativeDialog
        ss, _ = QtWidgets.QFileDialog.getOpenFileName(self,"Choose Samplesheet", "~","Sample sheet files (*.samplesheet *.ss)", options=ss_options)
        if ss:
            self.samplesheet_lineEdit.setText(ss)
            if self.runID_lineEdit.text() =='':
                self.runID_lineEdit.setText(ss.split('/')[-1].split('.')[0])


    def getToolscfg(self):
        tool_options = QtWidgets.QFileDialog.Options()
        tool_options |= QtWidgets.QFileDialog.DontUseNativeDialog
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs/tools_cfg/'
        file, _ = QtWidgets.QFileDialog.getOpenFileName(self,"Choose Tools configuration file", starting_folder,"Tools configuration files (*.cfg *.cfg.json)", options=tool_options)
        if file:
            self.workDir_lineEdit.setStyleSheet("color: black;")
            self.tools_lineEdit.setText(file)

    def getworkdir(self):
        wdir_options = QtWidgets.QFileDialog.Options()
        wdir_options |= QtWidgets.QFileDialog.DontUseNativeDialog
        wdir_options |= QtWidgets.QFileDialog.ShowDirsOnly
        wdir_options |= QtWidgets.QFileDialog.DontResolveSymlinks
        folder = QtWidgets.QFileDialog.getExistingDirectory(self,"Choose Working dir", "~" , options=wdir_options)
        if folder:
            self.workDir_lineEdit.setStyleSheet("color: black;")
            self.workDir_lineEdit.setText(folder)

    def get_workflow(self):
        workflow = []
        if self.item_pre_alig.checkState(0) != 0: workflow += ["prealignment"]
        if self.item_align.checkState(0) != 0: workflow += ["alignment"]
        if self.item_pre_proc.checkState(0) != 0: workflow += ["preprocessing"]
        #if self.item_vcalling.checkState(0) != 0: workflow += ["variant_calling"]
        if self.item_post_proc.checkState(0) != 0: workflow += ["postprocessing"]
        if self.item_ann.checkState(0) != 0: workflow += ["annotation"]
        if self.item_postann.checkState(0) != 0: workflow += ["postannotation"]

        if self.item_adapt.checkState(0) == 2: workflow += ["trim_adapters"]
        if self.item_len_filt.checkState(0) == 2: workflow += ["filter_fastq"]
        if self.item_q_filt.checkState(0) == 2: workflow += ["filter_fastq"]
        if self.item_fq_qc.checkState(0) == 2: workflow += ["fastq_QC"]
        if self.item_umi.checkState(0) == 2: workflow += ["merge_UMI"]
        if self.item_alig.checkState(0) == 2: workflow += ["fastq_alignment"]
        if self.item_sambam.checkState(0) == 2: workflow += ["sam_to_bam"]
        if self.item_sort.checkState(0) == 2: workflow += ["sortSam"]
        if self.item_bam_qc.checkState(0) == 2: workflow += ["bam_QC"]
        if self.item_bam_filt.checkState(0) == 2: workflow += ["filter_bam"]
        if self.item_rgroup.checkState(0) == 2: workflow += ["add_readgroups"]
        if self.item_dup.checkState(0) == 2: workflow += ["mark_pcr_dup"]
        if self.item_realig.checkState(0) == 2: workflow += ["indel_realignment"]
        if self.item_bqsr.checkState(0) == 2: workflow += ["BQ_recalibration"]
        if self.item_shortv_call.checkState(0) == 2: workflow += ["variant_calling"]
        if self.item_cnv_call.checkState(0) == 2: workflow += ["cnv_calling"]
        if self.item_vcf_norm.checkState(0) == 2: workflow += ["vcf_norm"]
        if self.item_vcf_filt.checkState(0) == 2: workflow += ["vcf_filter"]
        if self.item_vcf_to_tsv.checkState(0) == 2: workflow += ["vcf_to_tsv"]
        if self.item_shortv_ann.checkState(0) == 2: workflow += ["variant_ann"]
        if self.item_cnv_ann.checkState(0) == 2: workflow += ["cnv_ann"]
        if self.item_filt_ann.checkState(0) == 2: workflow += ["ann_filter"]
        if self.item_trs_filt_ann.checkState(0) == 2: workflow += ["trs_filter"]
        if self.item_vcf_ann_to_tsv.checkState(0) == 2: workflow += ["ann_vcf_to_tsv"]
        return workflow

    def add_to_queue(self):
        run,runid = self.retrieve_all_analysis_info()
        if run != None:
            if runid in self.analysis_dict["analysis_list"]:
                msg = QtWidgets.QMessageBox()
                msg.setWindowTitle("Analysis already exist")
                msg.setText("Do you want to replace it?")
                msg.setIcon(msg.Question)  
                msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel);
                x = msg.exec_()
                if x == QtWidgets.QMessageBox.Ok:
                    self.analysis_dict[runid] = run
            else:
                self.analysis_dict[runid] = run
                self.analysis_dict["analysis_list"] += [runid]
                self.analysis_list_QListWidget.addItem(runid)
        else:
            pass

    def show_analysis_info(self):
        runid = self.analysis_list_QListWidget.currentItem().text()
        start = MyMessageBox()
        start.setWindowTitle(runid)
        start.setText('\n'.join(['RunID: \t' + runid,
                'Panel: \t' + self.analysis_dict[runid]['panel'], 
                'Pipeline: \t' + self.analysis_dict[runid]['pipeline'],
                'Samplesheet: \t' + self.analysis_dict[runid]['samplesheet'],
                'Tools cfg: \t' + self.analysis_dict[runid]['toolscfg'],
                'WorkDir: \t' + self.analysis_dict[runid]['workdir'],
                'Delete temp files: \t' +  self.analysis_dict[runid]['del_temp'],
                'Sample parallization: \t' +  self.analysis_dict[runid]['paral']
                ]))
        returnValue = start.exec()

    def rem_from_queue(self):
        try:
            i = self.analysis_list_QListWidget.currentItem()
            runid = i.text()
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle(i.text())
            msg.setText("Do you want to delete it form queue?")
            msg.setIcon(msg.Question)  
            msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel);
            x = msg.exec_()
            if x == QtWidgets.QMessageBox.Ok:
                del self.analysis_dict[runid]
                self.analysis_dict["analysis_list"].remove(runid)
                row = self.analysis_list_QListWidget.row(i)
                self.analysis_list_QListWidget.takeItem(row)
        except:
            pass

    def set_step_treewidget(self):
        pipeline_dir = os.path.dirname(os.path.realpath(__file__))+'/configs/pipelines/'
        ss = pipeline_dir + self.pipeline_comboBox.currentText() + '.pipeline'
        if os.path.isfile(ss):
            self.pipeline = json.loads((open(ss).read()).encode('utf8'))
            
            STEP_workflow = self.pipeline["workflow"]

            if 'variantcalling' in STEP_workflow:
                self.item_shortv_call.setCheckState(0,2)
            else:
                self.item_shortv_call.setCheckState(0,0)

            if 'cnvcalling' in STEP_workflow:
                self.item_cnv_call.setCheckState(0,2) 
            else:
                self.item_cnv_call.setCheckState(0,0)

            if 'variant_annotation' in STEP_workflow:
                self.item_shortv_ann.setCheckState(0,2)
            else:
                self.item_shortv_ann.setCheckState(0,0)

            if 'cnv_annotation' in STEP_workflow:
                self.item_cnv_ann.setCheckState(0,2)
            else:
                self.item_cnv_ann.setCheckState(0,0)
                
            for STEP in STEP_workflow:
                try:
                    step_workflow = self.pipeline[STEP]["workflow"]
                    if STEP == 'prealignment':
                        if "trim_adapters" in step_workflow:
                            self.item_adapt.setCheckState(0,2)
                        else:
                            self.item_adapt.setCheckState(0,0)
                        if  "filter_fastq_by_len" in step_workflow:
                            self.item_len_filt.setCheckState(0,2)
                        else:
                            self.item_len_filt.setCheckState(0,0)
                        if "filter_fastq_by_qual" in step_workflow:
                            self.item_q_filt.setCheckState(0,2)
                        else:
                            self.item_q_filt.setCheckState(0,0)
                        if "fastq_QC" in step_workflow:
                            self.item_fq_qc.setCheckState(0,2)
                        else:
                            self.item_fq_qc.setCheckState(0,0)
                    if STEP == 'alignment':
                        if "merge_UMI" in step_workflow:
                            self.item_umi.setCheckState(0,2)
                        else:
                            self.item_umi.setCheckState(0,0)
                        if "fastq_alignment" in step_workflow:
                            self.item_alig.setCheckState(0,2)
                        else:
                            self.item_alig.setCheckState(0,0)
                        if "sam_to_bam" in step_workflow:
                            self.item_sambam.setCheckState(0,2)
                        else:
                            self.item_sambam.setCheckState(0,0)
                        if "sortSam" in step_workflow:
                            self.item_sort.setCheckState(0,2)
                        else:
                            self.item_sort.setCheckState(0,0)
                        if "bam_QC" in step_workflow:
                            self.item_bam_qc.setCheckState(0,2)
                        else:
                            self.item_bam_qc.setCheckState(0,0)
                    if STEP == 'preprocessing':
                        if "filter_bam" in step_workflow:
                            self.item_bam_filt.setCheckState(0,2)
                        else:    
                            self.item_bam_filt.setCheckState(0,0)
                        if "add_readgroups" in step_workflow:
                            self.item_rgroup.setCheckState(0,2)
                        else: 
                            self.item_rgroup.setCheckState(0,0)
                        if "mark_pcr_dup" in step_workflow:
                            self.item_dup.setCheckState(0,2)
                        else: 
                            self.item_dup.setCheckState(0,0)
                        if "indel_realignment" in step_workflow:
                            self.item_realig.setCheckState(0,2)
                        else: 
                            self.item_realig.setCheckState(0,0)
                        if "BQ_recalibration" in step_workflow:
                            self.item_bqsr.setCheckState(0,2)
                        else: 
                            self.item_bqsr.setCheckState(0,0)

                    if STEP == 'postprocessing':
                        if "vcf_filter" in step_workflow:
                            self.item_vcf_filt.setCheckState(0,2)
                        else: 
                            self.item_vcf_filt.setCheckState(0,0)
                        if "vcf_norm" in step_workflow:
                            self.item_vcf_norm.setCheckState(0,2)
                        else: 
                            self.item_vcf_norm.setCheckState(0,0)
                    #elif step == "Hard filter":
                        #self.treeWidget.topLevelItem(4).child(2).setCheckState(0,2)
                        if "vcf_to_tsv" in step_workflow:
                            self.item_vcf_to_tsv.setCheckState(0,2)
                        else: 
                            self.item_vcf_to_tsv.setCheckState(0,0)
                    if STEP == 'postannotation':       
                        if "ann_filter" in step_workflow:
                            self.item_filt_ann.setCheckState(0,2)
                        else: 
                            self.item_filt_ann.setCheckState(0,0)
                        if "filter_by_trs_list" in step_workflow:
                            self.item_trs_filt_ann.setCheckState(0,2)
                        else: 
                            self.item_trs_filt_ann.setCheckState(0,0)
                        if "ann_vcf_to_tsv" in step_workflow:
                            self.item_vcf_ann_to_tsv.setCheckState(0,2)
                        else: 
                            self.item_vcf_ann_to_tsv.setCheckState(0,0)
                except:
                    pass              


    def retrieve_all_analysis_info(self):
        runid = self.runID_lineEdit.text()
        panel = self.panels_comboBox.currentText()
        pipeline = self.pipeline_comboBox.currentText()
        samplesheet = self.samplesheet_lineEdit.text()
        workdir = '/'.join([self.workDir_lineEdit.text(),runid])
        toolscfg = self.tools_lineEdit.text()
        delete_temp = str(self.del_temp_checkBox.isChecked())
        paral = str(self.paral_checkBox.isChecked())
        #workflow = self.get_workflow()
        workflow='workflow'
        if runid == '':
            miss_runID = QtWidgets.QMessageBox()  
            miss_runID.setWindowTitle('Error!')
            miss_runID.setText('Invalid runID!')
            miss_runID.setIcon(QtWidgets.QMessageBox.Critical)
            miss_runID.exec()
            return None,None 

        elif not ((samplesheet.endswith('.ss') or  samplesheet.endswith('.samplesheet')) and os.path.exists(samplesheet)):
            miss_Samplesheet = QtWidgets.QMessageBox()
            miss_Samplesheet.setWindowTitle('Error!')
            miss_Samplesheet.setText('Invalid samplesheet!')
            miss_Samplesheet.setIcon(QtWidgets.QMessageBox.Critical)
            miss_Samplesheet.exec()
            return None,None

        else:
            start = MyMessageBox()
            start.setWindowTitle('Last Check')
            start.setText('\n\n'.join(['RunID: \t\t' + runid,
                'Panel: \t\t' + panel, 
                'Pipeline: \t\t' + pipeline,
                'Samplesheet: \t' + samplesheet,
                'Tools cfg: \t\t' + toolscfg,
                'WorkDir: \t\t' + workdir,
                'Delete temp files: \t' + delete_temp,
                'Sample parallization: \t' + paral]))
            returnValue = start.exec()
            if returnValue == 1:
                run = {"RunID":runid,
                    "panel":panel,
                    "pipeline":pipeline,
                    "samplesheet":samplesheet,
                    "toolscfg":toolscfg,
                    "workdir":workdir,
                    "del_temp":delete_temp,
                    "paral":paral
                }
                return run,runid
            else:
                return None,None
    

    def start_analysis(self):
        for row in range(self.analysis_list_QListWidget.count()):
            item = self.analysis_list_QListWidget.item(row)
            runid = item.text()
            panel = self.analysis_dict[runid]['panel']
            pipeline = self.analysis_dict[runid]['pipeline']
            samplesheet = self.analysis_dict[runid]['samplesheet']
            toolscfg = self.analysis_dict[runid]['toolscfg']
            workdir = self.analysis_dict[runid]['workdir']

            del_temp = self.analysis_dict[runid]['del_temp']
            paral = self.analysis_dict[runid]['paral']

            workflow = ','.join(self.get_workflow())

            powercall_main = '/'.join(os.path.dirname(os.path.realpath(__file__)).split('/')[:2] +['bin/main.py'])
            #args = ['gnome-terminal','-e', 'conda activate gatk && python /home/jarvis/print_a.py']
            #args = ['gnome-terminal', '-x', "python /home/jarvis/print_a.py"]
            status = subprocess.call('xterm -hold -e "conda run -n gatk python /home/jarvis/print_a.py"', shell=True)
            #success = subprocess.call(args)
            args = ['python3', powercall_main]
            args += ['--run_id', runid]
            args += ['--panel', panel]
            args += ['--analysis', pipeline]
            args += ['--workdir', workdir]
            args += ['--workflow', workflow]
            args += ['--samplesheet', samplesheet]
            args += ['--cfg', toolscfg]


            if del_temp == 'True': args += ['--del_temp']
            if paral == 'True': args += ['--del_temp']
            args += ['"']
            print(' '.join(args))
            #self.hide()
            #success = subprocess.call(args)
            # if not success:
            #     success = QtWidgets.QMessageBox()
            #     success.setWindowTitle('Success!')
            #     success.setText('The analysis has been successfully completed')
            #     success.setIcon(QtWidgets.QMessageBox.Information)
            #     success.exec()

    def init_functions(self):
        self.init_panels_combobox()
        self.init_pipeline_comboBox()
        self.start_analysis_pushButton.clicked.connect(self.start_analysis)
        self.samplesheet_toolButton.clicked.connect(self.getsamplesheet)
        self.workdir_toolButton.clicked.connect(self.getworkdir)
        self.tools_toolButton.clicked.connect(self.getToolscfg)
        self.pipeline_comboBox.currentTextChanged.connect(self.set_step_treewidget)
        self.analysis_list_QListWidget.doubleClicked.connect(self.show_analysis_info)
        self.add_queue_pushButton.clicked.connect(self.add_to_queue)
        self.rem_queue_pushButton.clicked.connect(self.rem_from_queue)


class MyMessageBox(QtWidgets.QDialog):   
    def __init__(self, parent = None):
        super(MyMessageBox, self).__init__(parent)
        self.setSizeGripEnabled(True)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("Dialog")
        self.resize(600, 400)
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")
        self.textBrowser = QtWidgets.QTextBrowser(self)
        self.textBrowser.setObjectName("textBrowser")
        self.verticalLayout.addWidget(self.textBrowser)
        self.buttonBox = QtWidgets.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        QtCore.QMetaObject.connectSlotsByName(self)

    def setText(self,text):
        self.textBrowser.append(text)