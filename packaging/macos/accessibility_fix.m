// Backport the ownership semantics of Qt commit 8148c48deb8e4345bacb797cb75c011df6f797fa.
// Native table rows/cells borrow Qt accessibility IDs; native teardown must not delete them.
// Built without ARC, matching Qt's Cocoa bridge. No Qt private headers or binary offsets.
#import <AppKit/AppKit.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <stdint.h>
#include <string.h>

static Ivar idVar, rowsVar, columnsVar, roleVar;
static Class elementClass;
static int installed;

static void invalidateElement(id self, SEL command)
{
    (void)command;
    const uint32_t zero = 0;
    memcpy((char *)self + ivar_getOffset(idVar), &zero, sizeof(zero));
    [object_getIvar(self, rowsVar) autorelease];
    object_setIvar(self, rowsVar, nil);
    [object_getIvar(self, columnsVar) autorelease];
    object_setIvar(self, columnsVar, nil);
    object_setIvar(self, roleVar, nil);
    NSAccessibilityPostNotification(self, NSAccessibilityUIElementDestroyedNotification);
}

static void deallocElement(id self, SEL command)
{
    [object_getIvar(self, rowsVar) release];
    [object_getIvar(self, columnsVar) release];
    struct objc_super parent = {self, class_getSuperclass(elementClass)};
    ((void (*)(struct objc_super *, SEL))objc_msgSendSuper)(&parent, command);
}

__attribute__((visibility("default"))) int skodacad_install_ax_fix(void)
{
    if (installed) return 2;
    elementClass = objc_getClass("QMacAccessibilityElement");
    if (!elementClass) return -1;
    idVar = class_getInstanceVariable(elementClass, "axid");
    rowsVar = class_getInstanceVariable(elementClass, "rows");
    columnsVar = class_getInstanceVariable(elementClass, "columns");
    roleVar = class_getInstanceVariable(elementClass, "synthesizedRole");
    if (!idVar || !rowsVar || !columnsVar || !roleVar) return -2;
    if (strcmp(ivar_getTypeEncoding(idVar), "I") != 0
            || ivar_getTypeEncoding(rowsVar)[0] != '@'
            || ivar_getTypeEncoding(columnsVar)[0] != '@'
            || ivar_getTypeEncoding(roleVar)[0] != '@') return -3;
    Method invalidate = class_getInstanceMethod(elementClass, sel_registerName("invalidate"));
    Method dealloc = class_getInstanceMethod(elementClass, sel_registerName("dealloc"));
    if (!invalidate || !dealloc || method_getNumberOfArguments(invalidate) != 2
            || method_getNumberOfArguments(dealloc) != 2) return -4;
    method_setImplementation(invalidate, (IMP)invalidateElement);
    method_setImplementation(dealloc, (IMP)deallocElement);
    installed = 1;
    return 1;
}

// Package regression: exercise native AX children and selected children of an owned Qt view.
// The caller checks that the Qt ID still resolves after draining the native autorelease pool.
__attribute__((visibility("default"))) int skodacad_probe_ax_table(uint32_t tableId)
{
    Class cls = objc_getClass("QMacAccessibilityElement");
    if (!cls || !tableId) return 0;
    @autoreleasepool {
        id element = ((id (*)(id, SEL, uint32_t))objc_msgSend)(
            (id)cls, sel_registerName("elementWithId:"), tableId);
        if (!element) return 0;
        NSArray *children = [NSArray arrayWithArray:[element accessibilityChildren]];
        if (![children count]) return 0;
        for (id child in children) {
            (void)[child accessibilityChildren];
            (void)[child accessibilitySelectedChildren];
        }
        if (![[element accessibilitySelectedChildren] count]) return 0;
    }
    return 1;
}
