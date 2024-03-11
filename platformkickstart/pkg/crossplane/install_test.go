package crossplane

import (
	"testing"

	"gotest.tools/v3/assert"
	corev1 "k8s.io/api/core/v1"
	v1 "k8s.io/apiextensions-apiserver/pkg/apis/apiextensions/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/dynamic/fake"
	kubernetestesting "k8s.io/client-go/testing"
)

func newFakeClient() *fake.FakeDynamicClient {
	client := fake.NewSimpleDynamicClient(runtime.NewScheme())
	// NewSimpleDynamicClient add reaction chains by default.
	client.ReactionChain = nil
	client.WatchReactionChain = nil
	client.ProxyReactionChain = nil
	return client
}

func TestXrdReady(t *testing.T) {
	testCases := map[string]struct {
		event watch.Event
		ready bool
		err   string
	}{
		"Ready": {
			event: watch.Event{Type: watch.Added},
			ready: true,
		},
		"Not ready": {
			event: watch.Event{Type: watch.Deleted},
			ready: false,
		},
	}

	for _, expected := range testCases {
		ready, err := xrdReady(expected.event)
		assert.Equal(t, ready, expected.ready)
		if expected.err != "" {
			assert.Error(t, err, expected.err)
		} else {
			assert.NilError(t, err)
		}
	}
}

func TestWaitForCrossplaneCRDs(t *testing.T) {
	t.Run("Created", func(t *testing.T) {
		client := newFakeClient()
		client.PrependWatchReactor(apiextensionsPlural, func(action kubernetestesting.Action) (handled bool, ret watch.Interface, err error) {
			res := watch.NewFake()
			go func() {
				crd := v1.CustomResourceDefinition{}
				res.Add(&crd)
			}()
			return true, res, nil
		})
		err := waitForCrossplaneCRDs(client)
		assert.NilError(t, err)
	})

	t.Run("Cannot create watcher", func(t *testing.T) {
		client := newFakeClient()
		err := waitForCrossplaneCRDs(client)
		assert.ErrorContains(t, err, "couldn't create watcher")
	})
}

func TestProviderReady(t *testing.T) {
	testCases := map[string]struct {
		event watch.Event
		ready bool
		err   string
	}{
		"Recently added provider is ready": {
			event: watch.Event{
				Type: watch.Added,
				Object: &unstructured.Unstructured{Object: map[string]interface{}{
					"status": map[string]interface{}{
						"conditions": []interface{}{
							map[string]interface{}{
								"type":   "Healthy",
								"status": "True",
							},
						},
					},
				}},
			},
			ready: true,
			err:   "",
		},
		"Modified provider is ready": {
			event: watch.Event{
				Type: watch.Modified,
				Object: &unstructured.Unstructured{Object: map[string]interface{}{
					"status": map[string]interface{}{
						"conditions": []interface{}{
							map[string]interface{}{
								"type":   "Healthy",
								"status": "True",
							},
						},
					},
				}},
			},
			ready: true,
			err:   "",
		},
		"Not ready": {
			event: watch.Event{
				Type: watch.Modified,
				Object: &unstructured.Unstructured{Object: map[string]interface{}{
					"status": map[string]interface{}{
						"conditions": []interface{}{
							map[string]interface{}{
								"type":   "Healthy",
								"status": "False",
							},
						},
					},
				}},
			},
			ready: false,
			err:   "",
		},
		"No status": {
			event: watch.Event{
				Type: watch.Modified,
				Object: &unstructured.Unstructured{Object: map[string]interface{}{
					"status": map[string]interface{}{
						"conditions": []interface{}{},
					},
				}},
			},
			ready: false,
			err:   "",
		},
		"Empty object": {
			event: watch.Event{
				Type:   watch.Modified,
				Object: &unstructured.Unstructured{},
			},
			ready: false,
			err:   "",
		},
		"Different object": {
			event: watch.Event{
				Type:   watch.Modified,
				Object: &corev1.Pod{},
			},
			ready: false,
			err:   "couldn't convert to unstructured",
		},
	}

	for _, expected := range testCases {
		ready, err := providerReady(expected.event)
		assert.Equal(t, ready, expected.ready)
		if expected.err != "" {
			assert.Error(t, err, expected.err)
		} else {
			assert.NilError(t, err)
		}
	}
}

func TestWaitForProvider(t *testing.T) {
	t.Run("Created", func(t *testing.T) {
		client := newFakeClient()
		client.PrependWatchReactor("providers", func(action kubernetestesting.Action) (handled bool, ret watch.Interface, err error) {
			res := watch.NewFake()
			go func() {
				object := unstructured.Unstructured{Object: map[string]interface{}{
					"status": map[string]interface{}{
						"conditions": []interface{}{
							map[string]interface{}{
								"type":   "Healthy",
								"status": "True",
							},
						},
					},
				}}
				res.Add(&object)
			}()
			return true, res, nil
		})
		err := WaitForProvider(client, "test")
		assert.NilError(t, err)
	})
	t.Run("Cannot create watcher", func(t *testing.T) {
		client := newFakeClient()
		err := WaitForProvider(client, "test")
		assert.ErrorContains(t, err, "couldn't create watcher")
	})
}
