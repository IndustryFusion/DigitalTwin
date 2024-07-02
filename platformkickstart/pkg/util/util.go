package util

import (
	"time"

	klog "k8s.io/klog/v2"
)

func LogEachTime(msg string, stop chan struct{}, ticker *time.Ticker) {
	for {
		select {
		case <-ticker.C:
			klog.Info(msg)
		case <-stop:
			return
		}
	}
}
