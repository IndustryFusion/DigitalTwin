package util

import (
	"context"
	"fmt"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/kubernetes"
)

const (
	FieldManager = "platform_kickstart"
)

func WaitForCondition(watcher watch.Interface, condition func(event watch.Event) (bool, error), timeout time.Duration) error {
	for {
		select {
		case <-time.After(timeout):
			return fmt.Errorf("timeout watching")
		case event := <-watcher.ResultChan():
			if meet, err := condition(event); meet {
				return err
			}
		}
	}
}

func KubeconfigFromConnectionSecret(cluster kubernetes.Interface, name, ns string) ([]byte, error) {
	secret, err := cluster.CoreV1().Secrets(ns).Get(context.Background(), name, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("couldn't get secret: %w", err)
	}

	kubeconfig, ok := secret.Data["kubeconfig"]
	if !ok {
		return nil, fmt.Errorf("no kubeconfig key in the %q secret", name)
	}

	return kubeconfig, nil
}
