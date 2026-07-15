// 香薰系统配置
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"
import "../../controls"

ScrollView {
    id: root
    clip: true

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        Text {
            text: "香薰系统"
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "硬件控制"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "启用香薰硬件"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }
                Item { Layout.fillWidth: true }
                XSwitch {
                    checked: settingsModel ? settingsModel.aromaEnabled : false
                    onToggled: if (settingsModel) settingsModel.aromaEnabled = checked
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text { text: "串口"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XTextField {
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.aromaSerialPort : ""
                    placeholderText: "Linux: /dev/ttyUSB0；Windows: COM3"
                    onEditingFinished: if (settingsModel) settingsModel.aromaSerialPort = text
                }

                Text { text: "波特率"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSpinBox {
                    Layout.fillWidth: true; from: 300; to: 115200; stepSize: 300
                    value: settingsModel ? settingsModel.aromaBaudrate : 9600
                    onValueModified: if (settingsModel) settingsModel.aromaBaudrate = value
                }

                Text { text: "设备地址"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSpinBox {
                    Layout.fillWidth: true; from: 1; to: 254
                    value: settingsModel ? settingsModel.aromaDeviceAddress : 254
                    onValueModified: if (settingsModel) settingsModel.aromaDeviceAddress = value
                }

                Text { text: "串口超时（秒）"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSpinBox {
                    Layout.fillWidth: true; from: 1; to: 30; stepSize: 1
                    value: settingsModel ? settingsModel.aromaSerialTimeout : 1
                    onValueModified: if (settingsModel) settingsModel.aromaSerialTimeout = value
                }

                Text { text: "重试次数"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSpinBox {
                    Layout.fillWidth: true; from: 0; to: 5
                    value: settingsModel ? settingsModel.aromaRetries : 1
                    onValueModified: if (settingsModel) settingsModel.aromaRetries = value
                }

                Text { text: "有效电平"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSwitch {
                    checked: settingsModel ? settingsModel.aromaActiveHigh : true
                    onToggled: if (settingsModel) settingsModel.aromaActiveHigh = checked
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "配方输出"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text { text: "配方模式"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XComboBox {
                    Layout.fillWidth: true
                    model: ["binary", "concentration"]
                    currentIndex: settingsModel && settingsModel.aromaPatternMode === "concentration" ? 1 : 0
                    onActivated: if (settingsModel) settingsModel.aromaPatternMode = currentText
                }

                Text { text: "默认浓度"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                XSpinBox {
                    Layout.fillWidth: true; from: 1; to: 100
                    value: settingsModel ? settingsModel.aromaDefaultConcentration : 100
                    onValueModified: if (settingsModel) settingsModel.aromaDefaultConcentration = value
                }
            }

            Text {
                text: "16 路香型映射（JSON；香型名称对应通道 1–16）"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 170
                text: settingsModel ? settingsModel.aromaChannelMap : "{}"
                wrapMode: TextArea.Wrap
                onEditingFinished: if (settingsModel) settingsModel.aromaChannelMap = text
                placeholderText: '{"lavender": 1, "bergamot": 2, ...}'
            }
        }

        Text {
            Layout.fillWidth: true
            text: "保存后重启语音服务。首次接线测试请断开负载，并确认串口、地址、有效电平和通道映射。"
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textPlaceholder
            wrapMode: Text.WordWrap
        }
        Item { Layout.fillHeight: true }
    }
}
