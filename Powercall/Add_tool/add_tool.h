#ifndef ADD_TOOL_H
#define ADD_TOOL_H

#include <QWidget>

QT_BEGIN_NAMESPACE
namespace Ui { class Add_tool; }
QT_END_NAMESPACE

class Add_tool : public QWidget
{
    Q_OBJECT

public:
    Add_tool(QWidget *parent = nullptr);
    ~Add_tool();

private:
    Ui::Add_tool *ui;
};
#endif // ADD_TOOL_H
