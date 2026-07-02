import QtQuick
import QtQuick.Controls
import QtMultimedia

/*
  MileHologram

  用途：
  - 单独的 弥勒 三维投影前端组件
  - 可直接替换原来的 emoji / 头像区域
  - 默认循环播放对应视频资源

  放置结构建议：
  components/MileHologram.qml
  assets/弥勒_三维投影.mp4

  使用示例：
  MileHologram {
      anchors.centerIn: parent
      width: 420
      height: 420
      showStatusText: false
      statusText: "待命"
  }
*/

Item {
    id: root

    width: 420
    height: 420

    property bool showStatusText: true
    property bool autoPlay: true
    property bool muted: true
    property real videoScale: 1.0
    property color backgroundColor: "black"
    property color textColor: "#D6D9E0"
    property int radius: 0

    property url videoSource: Qt.resolvedUrl("../../../../../assets/mile.mp4")

    signal clicked()

    function play() {
        player.play()
    }

    function pause() {
        player.pause()
    }

    function restart() {
        player.stop()
        player.play()
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: root.radius
        clip: true

        MediaPlayer {
            id: player
            source: root.videoSource
            loops: MediaPlayer.Infinite
            audioOutput: AudioOutput {
                volume: root.muted ? 0 : 1
            }
            videoOutput: videoOutput

            Component.onCompleted: {
                if (root.autoPlay) {
                    player.play()
                }
            }
        }

        VideoOutput {
            id: videoOutput
            anchors.centerIn: parent
            width: parent.width * root.videoScale
            height: parent.height * root.videoScale
            fillMode: VideoOutput.PreserveAspectFit
            antialiasing: true
        }

        Text {
            visible: root.showStatusText
            text: root.statusText
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Math.max(10, parent.height * 0.045)
            color: root.textColor
            font.pixelSize: Math.max(14, parent.height * 0.045)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.clicked()
                if (player.playbackState === MediaPlayer.PlayingState) {
                    player.pause()
                } else {
                    player.play()
                }
            }
        }
    }
}
