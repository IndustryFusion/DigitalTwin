package util

import (
	"testing"
	"time"

	"gotest.tools/v3/assert"
	klog "k8s.io/klog/v2"
)

func TestLogEachTime(t *testing.T) {
	stop := make(chan struct{})
	ticker := time.NewTicker(time.Second / 3)
	go func() {
		time.Sleep(time.Second)
		close(stop)
	}()
	klog.Flush()
	LogEachTime("test", stop, ticker)
	assert.Equal(t, klog.Stats.Info.Lines(), int64(3))
}
