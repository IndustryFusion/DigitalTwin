package util

import (
	"fmt"
	"os"
	"testing"
	"time"

	"gotest.tools/v3/assert"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/watch"
	kubernetesfake "k8s.io/client-go/kubernetes/fake"
)

func TestKubeconfigFromConnectionSecret(t *testing.T) {
	fakeKubeconfig, err := os.ReadFile("testdata/kubeconfig")
	assert.NilError(t, err)

	testcases := map[string]struct {
		client     *kubernetesfake.Clientset
		secretName string
		namespace  string
		bytes      []byte
		err        string
	}{
		"Proper kubeconfig": {
			client: kubernetesfake.NewSimpleClientset(&corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Data: map[string][]byte{
					"kubeconfig": fakeKubeconfig,
				},
			}),
			secretName: "test",
			namespace:  "default",
			bytes:      fakeKubeconfig,
			err:        "",
		},
		"No secret": {
			client:     kubernetesfake.NewSimpleClientset(),
			secretName: "test",
			namespace:  "default",
			bytes:      nil,
			err:        `couldn't get secret: secrets "test" not found`,
		},
		"No kubeconfig": {
			client: kubernetesfake.NewSimpleClientset(&corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Data: map[string][]byte{},
			}),
			secretName: "test",
			namespace:  "default",
			bytes:      nil,
			err:        `no kubeconfig key in the "test" secret`,
		},
	}

	for name, tc := range testcases {
		t.Run(name, func(t *testing.T) {
			bytes, err := KubeconfigFromConnectionSecret(tc.client, tc.secretName, tc.namespace)
			if tc.err != "" {
				assert.Error(t, err, tc.err)
			}
			assert.DeepEqual(t, bytes, tc.bytes)
		})
	}
}

func TestWaitForCondition(t *testing.T) {
	t.Run("Timeout occurred", func(t *testing.T) {
		watcher := watch.NewFake()
		err := WaitForCondition(watcher, func(event watch.Event) (bool, error) {
			return false, nil
		}, time.Second)
		assert.Error(t, err, "timeout watching")
	})
	t.Run("Condition meet", func(t *testing.T) {
		watcher := watch.NewFake()
		go func() {
			object := map[string]interface{}{"metadata": map[string]interface{}{"name": "test"}}
			watcher.Add(&unstructured.Unstructured{Object: object})
		}()
		err := WaitForCondition(watcher, func(event watch.Event) (condition bool, err error) {
			if event.Type == watch.Added {
				object, ok := event.Object.(*unstructured.Unstructured)
				if !ok {
					err = fmt.Errorf("couldn't convert to unstructured")
					return
				}
				if object.GetName() == "test" {
					condition = true
				}
			}
			return
		}, time.Second)
		assert.NilError(t, err)
	})
}

func TestCreateKindCluster(t *testing.T) {}
