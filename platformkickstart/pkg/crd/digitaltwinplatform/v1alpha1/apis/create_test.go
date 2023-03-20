package apis

import (
	"fmt"
	"github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1"
	crossplanev1 "github.com/crossplane/crossplane-runtime/apis/common/v1"
	"gotest.tools/v3/assert"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
	kubernetestesting "k8s.io/client-go/testing"
	"testing"

	platformfake "github.com/IndustryFusion/DigitalTwin/platformkickstart/pkg/crd/digitaltwinplatform/v1alpha1/apis/clientset/versioned/fake"
)

func newFakeClient() *platformfake.Clientset {
	client := platformfake.NewSimpleClientset()
	// NewSimpleDynamicClient add reaction chains by default.
	client.ReactionChain = nil
	client.WatchReactionChain = nil
	client.ProxyReactionChain = nil
	return client
}

func TestCreateForDigitalTwinPlatform(t *testing.T) {
	t.Run("Recently created", func(t *testing.T) {
		client := newFakeClient()
		client.PrependWatchReactor(v1alpha1.Plural, func(action kubernetestesting.Action) (handled bool, ret watch.Interface, err error) {
			res := watch.NewFake()
			go func() {
				platform := v1alpha1.DigitalTwinPlatform{
					TypeMeta: metav1.TypeMeta{
						Kind:       v1alpha1.Kind,
						APIVersion: v1alpha1.APIVersion,
					},
					ObjectMeta: metav1.ObjectMeta{Name: "test"},
				}
				platform.Status.SetConditions(crossplanev1.Condition{
					Type:   crossplanev1.TypeReady,
					Status: corev1.ConditionTrue,
				})
				res.Add(&platform)
			}()
			return true, res, nil
		})
		err := CreateDigitalTwinPlatform(client, v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       v1alpha1.Kind,
				APIVersion: v1alpha1.APIVersion,
			},
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
		})
		assert.NilError(t, err)
	})
	t.Run("Already deployed", func(t *testing.T) {
		client := newFakeClient()
		client.PrependWatchReactor(v1alpha1.Plural, func(action kubernetestesting.Action) (handled bool, ret watch.Interface, err error) {
			res := watch.NewFake()
			go func() {
				platform := v1alpha1.DigitalTwinPlatform{
					TypeMeta: metav1.TypeMeta{
						Kind:       v1alpha1.Kind,
						APIVersion: v1alpha1.APIVersion,
					},
					ObjectMeta: metav1.ObjectMeta{Name: "test"},
				}
				platform.Status.SetConditions(crossplanev1.Condition{
					Type:   crossplanev1.TypeReady,
					Status: corev1.ConditionTrue,
				})
				res.Modify(&platform)
			}()
			return true, res, nil
		})
		err := CreateDigitalTwinPlatform(client, v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       v1alpha1.Kind,
				APIVersion: v1alpha1.APIVersion,
			},
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
		})
		assert.NilError(t, err)
	})
	t.Run("Couldn't create", func(t *testing.T) {
		client := newFakeClient()
		client.PrependReactor("patch", v1alpha1.Plural, func(action kubernetestesting.Action) (handled bool, ret runtime.Object, err error) {
			return true, nil, fmt.Errorf("not registered")
		})
		err := CreateDigitalTwinPlatform(client, v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       v1alpha1.Kind,
				APIVersion: v1alpha1.APIVersion,
			},
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
		})
		assert.ErrorContains(t, err, "couldn't create object")
	})
	t.Run("Cannot watch", func(t *testing.T) {
		client := newFakeClient()
		err := CreateDigitalTwinPlatform(client, v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       v1alpha1.Kind,
				APIVersion: v1alpha1.APIVersion,
			},
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
		})
		assert.ErrorContains(t, err, "couldn't create watcher")
	})
}

func TestDigitalTwinPlatformCondition(t *testing.T) {
	t.Run("DigitalTwinPlatform is ready", func(t *testing.T) {
		platform := v1alpha1.DigitalTwinPlatform{
			TypeMeta: metav1.TypeMeta{
				Kind:       v1alpha1.Kind,
				APIVersion: v1alpha1.APIVersion,
			},
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
		}
		platform.Status.SetConditions(crossplanev1.Condition{Type: crossplanev1.TypeReady, Status: corev1.ConditionTrue})

		ready, err := digitalTwinPlatformReady(watch.Event{
			Type:   watch.Modified,
			Object: &platform,
		})
		assert.Equal(t, ready, true)
		assert.NilError(t, err)
	})
}
