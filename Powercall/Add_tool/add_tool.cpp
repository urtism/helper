#include "add_tool.h"
#include "ui_add_tool.h"

Add_tool::Add_tool(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Add_tool)
{
    ui->setupUi(this);
}

Add_tool::~Add_tool()
{
    delete ui;
}

