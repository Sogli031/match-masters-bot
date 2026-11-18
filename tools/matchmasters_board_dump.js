📦
267358 /matchmasters_board_dump.js
✄
// node_modules/frida-il2cpp-bridge/dist/index.js
var __decorate = function(decorators, target, key, desc) {
  var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
  if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
  else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
  return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var Il2Cpp2;
(function(Il2Cpp3) {
  Il2Cpp3.application = {
    /**
     * Gets the data path name of the current application, e.g.
     * `/data/emulated/0/Android/data/com.example.application/files`
     * on Android.
     *
     * **This information is not guaranteed to exist.**
     *
     * ```ts
     * Il2Cpp.perform(() => {
     *     // prints /data/emulated/0/Android/data/com.example.application/files
     *     console.log(Il2Cpp.application.dataPath);
     * });
     * ```
     */
    get dataPath() {
      return unityEngineCall("get_persistentDataPath");
    },
    /**
     * Gets the identifier name of the current application, e.g.
     * `com.example.application` on Android.
     *
     * In case the identifier cannot be retrieved, the main module name is
     * returned instead, which typically is the process name.
     *
     * ```ts
     * Il2Cpp.perform(() => {
     *     // prints com.example.application
     *     console.log(Il2Cpp.application.identifier);
     * });
     * ```
     */
    get identifier() {
      return unityEngineCall("get_identifier") ?? unityEngineCall("get_bundleIdentifier") ?? Process.mainModule.name;
    },
    /**
     * Gets the version name of the current application, e.g. `4.12.8`.
     *
     * In case the version cannot be retrieved, an hash of the IL2CPP
     * module is returned instead.
     *
     * ```ts
     * Il2Cpp.perform(() => {
     *     // prints 4.12.8
     *     console.log(Il2Cpp.application.version);
     * });
     * ```
     */
    get version() {
      return unityEngineCall("get_version") ?? exportsHash(Il2Cpp3.module).toString(16);
    }
  };
  getter(Il2Cpp3, "unityVersion", () => {
    try {
      const unityVersion = Il2Cpp3.$config.unityVersion ?? unityEngineCall("get_unityVersion");
      if (unityVersion != null) {
        return unityVersion;
      }
    } catch (_) {
    }
    const searchPattern = "69 6c 32 63 70 70";
    for (const range of Il2Cpp3.module.enumerateRanges("r--").concat(Process.getRangeByAddress(Il2Cpp3.module.base))) {
      for (let { address } of Memory.scanSync(range.base, range.size, searchPattern)) {
        while (address.readU8() != 0) {
          address = address.sub(1);
        }
        const match = UnityVersion.find(address.add(1).readCString());
        if (match != void 0) {
          return match;
        }
      }
    }
    raise("couldn't determine the Unity version, please specify it manually");
  }, lazy);
  getter(Il2Cpp3, "unityVersionIsBelow201830", () => {
    return UnityVersion.lt(Il2Cpp3.unityVersion, "2018.3.0");
  }, lazy);
  getter(Il2Cpp3, "unityVersionIsBelow202120", () => {
    return UnityVersion.lt(Il2Cpp3.unityVersion, "2021.2.0");
  }, lazy);
  function unityEngineCall(method) {
    const handle = Il2Cpp3.exports.resolveInternalCall(Memory.allocUtf8String("UnityEngine.Application::" + method));
    const nativeFunction = new NativeFunction(handle, "pointer", []);
    return nativeFunction.isNull() ? null : new Il2Cpp3.String(nativeFunction()).asNullable()?.content ?? null;
  }
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function boxed(value, type) {
    const mapping = {
      int8: "System.SByte",
      uint8: "System.Byte",
      int16: "System.Int16",
      uint16: "System.UInt16",
      int32: "System.Int32",
      uint32: "System.UInt32",
      int64: "System.Int64",
      uint64: "System.UInt64",
      char: "System.Char",
      intptr: "System.IntPtr",
      uintptr: "System.UIntPtr"
    };
    const className = typeof value == "boolean" ? "System.Boolean" : typeof value == "number" ? mapping[type ?? "int32"] : value instanceof Int64 ? "System.Int64" : value instanceof UInt64 ? "System.UInt64" : value instanceof NativePointer ? mapping[type ?? "intptr"] : raise(`Cannot create boxed primitive using value of type '${typeof value}'`);
    const object = Il2Cpp3.corlib.class(className ?? raise(`Unknown primitive type name '${type}'`)).alloc();
    (object.tryField("m_value") ?? object.tryField("_pointer") ?? raise(`Could not find primitive field in class '${className}'`)).value = value;
    return object;
  }
  Il2Cpp3.boxed = boxed;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  Il2Cpp3.$config = {
    moduleName: void 0,
    unityVersion: void 0,
    exports: void 0
  };
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function dump(fileName, path) {
    fileName = fileName ?? `${Il2Cpp3.application.identifier}_${Il2Cpp3.application.version}.cs`;
    path = path ?? Il2Cpp3.application.dataPath ?? Process.getCurrentDir();
    createDirectoryRecursively(path);
    const destination = `${path}/${fileName}`;
    const file = new File(destination, "w");
    for (const assembly of Il2Cpp3.domain.assemblies) {
      inform(`dumping ${assembly.name}...`);
      for (const klass of assembly.image.classes) {
        file.write(`${klass}

`);
      }
    }
    file.flush();
    file.close();
    ok(`dump saved to ${destination}`);
    showDeprecationNotice();
  }
  Il2Cpp3.dump = dump;
  function dumpTree(path, ignoreAlreadyExistingDirectory = false) {
    path = path ?? `${Il2Cpp3.application.dataPath ?? Process.getCurrentDir()}/${Il2Cpp3.application.identifier}_${Il2Cpp3.application.version}`;
    if (!ignoreAlreadyExistingDirectory && directoryExists(path)) {
      raise(`directory ${path} already exists - pass ignoreAlreadyExistingDirectory = true to skip this check`);
    }
    for (const assembly of Il2Cpp3.domain.assemblies) {
      inform(`dumping ${assembly.name}...`);
      const destination = `${path}/${assembly.name.replaceAll(".", "/")}.cs`;
      createDirectoryRecursively(destination.substring(0, destination.lastIndexOf("/")));
      const file = new File(destination, "w");
      for (const klass of assembly.image.classes) {
        file.write(`${klass}

`);
      }
      file.flush();
      file.close();
    }
    ok(`dump saved to ${path}`);
    showDeprecationNotice();
  }
  Il2Cpp3.dumpTree = dumpTree;
  function directoryExists(path) {
    return Il2Cpp3.corlib.class("System.IO.Directory").method("Exists").invoke(Il2Cpp3.string(path));
  }
  function createDirectoryRecursively(path) {
    Il2Cpp3.corlib.class("System.IO.Directory").method("CreateDirectory").invoke(Il2Cpp3.string(path));
  }
  function showDeprecationNotice() {
    warn("this api will be removed in a future release, please use `npx frida-il2cpp-bridge dump` instead");
  }
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function installExceptionListener(targetThread = "current") {
    const currentThread = Il2Cpp3.exports.threadGetCurrent();
    return Interceptor.attach(Il2Cpp3.module.getExportByName("__cxa_throw"), function(args) {
      if (targetThread == "current" && !Il2Cpp3.exports.threadGetCurrent().equals(currentThread)) {
        return;
      }
      inform(new Il2Cpp3.Object(args[0].readPointer()));
    });
  }
  Il2Cpp3.installExceptionListener = installExceptionListener;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  Il2Cpp3.exports = {
    get alloc() {
      return r("il2cpp_alloc", "pointer", ["size_t"]);
    },
    get arrayGetLength() {
      return r("il2cpp_array_length", "uint32", ["pointer"]);
    },
    get arrayNew() {
      return r("il2cpp_array_new", "pointer", ["pointer", "uint32"]);
    },
    get assemblyGetImage() {
      return r("il2cpp_assembly_get_image", "pointer", ["pointer"]);
    },
    get classForEach() {
      return r("il2cpp_class_for_each", "void", ["pointer", "pointer"]);
    },
    get classFromName() {
      return r("il2cpp_class_from_name", "pointer", ["pointer", "pointer", "pointer"]);
    },
    get classFromObject() {
      return r("il2cpp_class_from_system_type", "pointer", ["pointer"]);
    },
    get classGetArrayClass() {
      return r("il2cpp_array_class_get", "pointer", ["pointer", "uint32"]);
    },
    get classGetArrayElementSize() {
      return r("il2cpp_class_array_element_size", "int", ["pointer"]);
    },
    get classGetAssemblyName() {
      return r("il2cpp_class_get_assemblyname", "pointer", ["pointer"]);
    },
    get classGetBaseType() {
      return r("il2cpp_class_enum_basetype", "pointer", ["pointer"]);
    },
    get classGetDeclaringType() {
      return r("il2cpp_class_get_declaring_type", "pointer", ["pointer"]);
    },
    get classGetElementClass() {
      return r("il2cpp_class_get_element_class", "pointer", ["pointer"]);
    },
    get classGetFieldFromName() {
      return r("il2cpp_class_get_field_from_name", "pointer", ["pointer", "pointer"]);
    },
    get classGetFields() {
      return r("il2cpp_class_get_fields", "pointer", ["pointer", "pointer"]);
    },
    get classGetFlags() {
      return r("il2cpp_class_get_flags", "int", ["pointer"]);
    },
    get classGetImage() {
      return r("il2cpp_class_get_image", "pointer", ["pointer"]);
    },
    get classGetInstanceSize() {
      return r("il2cpp_class_instance_size", "int32", ["pointer"]);
    },
    get classGetInterfaces() {
      return r("il2cpp_class_get_interfaces", "pointer", ["pointer", "pointer"]);
    },
    get classGetMethodFromName() {
      return r("il2cpp_class_get_method_from_name", "pointer", ["pointer", "pointer", "int"]);
    },
    get classGetMethods() {
      return r("il2cpp_class_get_methods", "pointer", ["pointer", "pointer"]);
    },
    get classGetName() {
      return r("il2cpp_class_get_name", "pointer", ["pointer"]);
    },
    get classGetNamespace() {
      return r("il2cpp_class_get_namespace", "pointer", ["pointer"]);
    },
    get classGetNestedClasses() {
      return r("il2cpp_class_get_nested_types", "pointer", ["pointer", "pointer"]);
    },
    get classGetParent() {
      return r("il2cpp_class_get_parent", "pointer", ["pointer"]);
    },
    get classGetStaticFieldData() {
      return r("il2cpp_class_get_static_field_data", "pointer", ["pointer"]);
    },
    get classGetValueTypeSize() {
      return r("il2cpp_class_value_size", "int32", ["pointer", "pointer"]);
    },
    get classGetType() {
      return r("il2cpp_class_get_type", "pointer", ["pointer"]);
    },
    get classHasReferences() {
      return r("il2cpp_class_has_references", "bool", ["pointer"]);
    },
    get classInitialize() {
      return r("il2cpp_runtime_class_init", "void", ["pointer"]);
    },
    get classIsAbstract() {
      return r("il2cpp_class_is_abstract", "bool", ["pointer"]);
    },
    get classIsAssignableFrom() {
      return r("il2cpp_class_is_assignable_from", "bool", ["pointer", "pointer"]);
    },
    get classIsBlittable() {
      return r("il2cpp_class_is_blittable", "bool", ["pointer"]);
    },
    get classIsEnum() {
      return r("il2cpp_class_is_enum", "bool", ["pointer"]);
    },
    get classIsGeneric() {
      return r("il2cpp_class_is_generic", "bool", ["pointer"]);
    },
    get classIsInflated() {
      return r("il2cpp_class_is_inflated", "bool", ["pointer"]);
    },
    get classIsInterface() {
      return r("il2cpp_class_is_interface", "bool", ["pointer"]);
    },
    get classIsSubclassOf() {
      return r("il2cpp_class_is_subclass_of", "bool", ["pointer", "pointer", "bool"]);
    },
    get classIsValueType() {
      return r("il2cpp_class_is_valuetype", "bool", ["pointer"]);
    },
    get domainGetAssemblyFromName() {
      return r("il2cpp_domain_assembly_open", "pointer", ["pointer", "pointer"]);
    },
    get domainGet() {
      return r("il2cpp_domain_get", "pointer", []);
    },
    get domainGetAssemblies() {
      return r("il2cpp_domain_get_assemblies", "pointer", ["pointer", "pointer"]);
    },
    get fieldGetClass() {
      return r("il2cpp_field_get_parent", "pointer", ["pointer"]);
    },
    get fieldGetFlags() {
      return r("il2cpp_field_get_flags", "int", ["pointer"]);
    },
    get fieldGetName() {
      return r("il2cpp_field_get_name", "pointer", ["pointer"]);
    },
    get fieldGetOffset() {
      return r("il2cpp_field_get_offset", "int32", ["pointer"]);
    },
    get fieldGetStaticValue() {
      return r("il2cpp_field_static_get_value", "void", ["pointer", "pointer"]);
    },
    get fieldGetType() {
      return r("il2cpp_field_get_type", "pointer", ["pointer"]);
    },
    get fieldSetStaticValue() {
      return r("il2cpp_field_static_set_value", "void", ["pointer", "pointer"]);
    },
    get free() {
      return r("il2cpp_free", "void", ["pointer"]);
    },
    get gcCollect() {
      return r("il2cpp_gc_collect", "void", ["int"]);
    },
    get gcCollectALittle() {
      return r("il2cpp_gc_collect_a_little", "void", []);
    },
    get gcDisable() {
      return r("il2cpp_gc_disable", "void", []);
    },
    get gcEnable() {
      return r("il2cpp_gc_enable", "void", []);
    },
    get gcGetHeapSize() {
      return r("il2cpp_gc_get_heap_size", "int64", []);
    },
    get gcGetMaxTimeSlice() {
      return r("il2cpp_gc_get_max_time_slice_ns", "int64", []);
    },
    get gcGetUsedSize() {
      return r("il2cpp_gc_get_used_size", "int64", []);
    },
    get gcHandleGetTarget() {
      return r("il2cpp_gchandle_get_target", "pointer", ["uint32"]);
    },
    get gcHandleFree() {
      return r("il2cpp_gchandle_free", "void", ["uint32"]);
    },
    get gcHandleNew() {
      return r("il2cpp_gchandle_new", "uint32", ["pointer", "bool"]);
    },
    get gcHandleNewWeakRef() {
      return r("il2cpp_gchandle_new_weakref", "uint32", ["pointer", "bool"]);
    },
    get gcIsDisabled() {
      return r("il2cpp_gc_is_disabled", "bool", []);
    },
    get gcIsIncremental() {
      return r("il2cpp_gc_is_incremental", "bool", []);
    },
    get gcSetMaxTimeSlice() {
      return r("il2cpp_gc_set_max_time_slice_ns", "void", ["int64"]);
    },
    get gcStartIncrementalCollection() {
      return r("il2cpp_gc_start_incremental_collection", "void", []);
    },
    get gcStartWorld() {
      return r("il2cpp_start_gc_world", "void", []);
    },
    get gcStopWorld() {
      return r("il2cpp_stop_gc_world", "void", []);
    },
    get getCorlib() {
      return r("il2cpp_get_corlib", "pointer", []);
    },
    get imageGetAssembly() {
      return r("il2cpp_image_get_assembly", "pointer", ["pointer"]);
    },
    get imageGetClass() {
      return r("il2cpp_image_get_class", "pointer", ["pointer", "uint"]);
    },
    get imageGetClassCount() {
      return r("il2cpp_image_get_class_count", "uint32", ["pointer"]);
    },
    get imageGetName() {
      return r("il2cpp_image_get_name", "pointer", ["pointer"]);
    },
    get initialize() {
      return r("il2cpp_init", "void", ["pointer"]);
    },
    get livenessAllocateStruct() {
      return r("il2cpp_unity_liveness_allocate_struct", "pointer", ["pointer", "int", "pointer", "pointer", "pointer"]);
    },
    get livenessCalculationBegin() {
      return r("il2cpp_unity_liveness_calculation_begin", "pointer", ["pointer", "int", "pointer", "pointer", "pointer", "pointer"]);
    },
    get livenessCalculationEnd() {
      return r("il2cpp_unity_liveness_calculation_end", "void", ["pointer"]);
    },
    get livenessCalculationFromStatics() {
      return r("il2cpp_unity_liveness_calculation_from_statics", "void", ["pointer"]);
    },
    get livenessFinalize() {
      return r("il2cpp_unity_liveness_finalize", "void", ["pointer"]);
    },
    get livenessFreeStruct() {
      return r("il2cpp_unity_liveness_free_struct", "void", ["pointer"]);
    },
    get memorySnapshotCapture() {
      return r("il2cpp_capture_memory_snapshot", "pointer", []);
    },
    get memorySnapshotFree() {
      return r("il2cpp_free_captured_memory_snapshot", "void", ["pointer"]);
    },
    get memorySnapshotGetClasses() {
      return r("il2cpp_memory_snapshot_get_classes", "pointer", ["pointer", "pointer"]);
    },
    get memorySnapshotGetObjects() {
      return r("il2cpp_memory_snapshot_get_objects", "pointer", ["pointer", "pointer"]);
    },
    get methodGetClass() {
      return r("il2cpp_method_get_class", "pointer", ["pointer"]);
    },
    get methodGetFlags() {
      return r("il2cpp_method_get_flags", "uint32", ["pointer", "pointer"]);
    },
    get methodGetName() {
      return r("il2cpp_method_get_name", "pointer", ["pointer"]);
    },
    get methodGetObject() {
      return r("il2cpp_method_get_object", "pointer", ["pointer", "pointer"]);
    },
    get methodGetParameterCount() {
      return r("il2cpp_method_get_param_count", "uint8", ["pointer"]);
    },
    get methodGetParameterName() {
      return r("il2cpp_method_get_param_name", "pointer", ["pointer", "uint32"]);
    },
    get methodGetParameters() {
      return r("il2cpp_method_get_parameters", "pointer", ["pointer", "pointer"]);
    },
    get methodGetParameterType() {
      return r("il2cpp_method_get_param", "pointer", ["pointer", "uint32"]);
    },
    get methodGetReturnType() {
      return r("il2cpp_method_get_return_type", "pointer", ["pointer"]);
    },
    get methodIsGeneric() {
      return r("il2cpp_method_is_generic", "bool", ["pointer"]);
    },
    get methodIsInflated() {
      return r("il2cpp_method_is_inflated", "bool", ["pointer"]);
    },
    get methodIsInstance() {
      return r("il2cpp_method_is_instance", "bool", ["pointer"]);
    },
    get monitorEnter() {
      return r("il2cpp_monitor_enter", "void", ["pointer"]);
    },
    get monitorExit() {
      return r("il2cpp_monitor_exit", "void", ["pointer"]);
    },
    get monitorPulse() {
      return r("il2cpp_monitor_pulse", "void", ["pointer"]);
    },
    get monitorPulseAll() {
      return r("il2cpp_monitor_pulse_all", "void", ["pointer"]);
    },
    get monitorTryEnter() {
      return r("il2cpp_monitor_try_enter", "bool", ["pointer", "uint32"]);
    },
    get monitorTryWait() {
      return r("il2cpp_monitor_try_wait", "bool", ["pointer", "uint32"]);
    },
    get monitorWait() {
      return r("il2cpp_monitor_wait", "void", ["pointer"]);
    },
    get objectGetClass() {
      return r("il2cpp_object_get_class", "pointer", ["pointer"]);
    },
    get objectGetVirtualMethod() {
      return r("il2cpp_object_get_virtual_method", "pointer", ["pointer", "pointer"]);
    },
    get objectInitialize() {
      return r("il2cpp_runtime_object_init_exception", "void", ["pointer", "pointer"]);
    },
    get objectNew() {
      return r("il2cpp_object_new", "pointer", ["pointer"]);
    },
    get objectGetSize() {
      return r("il2cpp_object_get_size", "uint32", ["pointer"]);
    },
    get objectUnbox() {
      return r("il2cpp_object_unbox", "pointer", ["pointer"]);
    },
    get resolveInternalCall() {
      return r("il2cpp_resolve_icall", "pointer", ["pointer"]);
    },
    get stringGetChars() {
      return r("il2cpp_string_chars", "pointer", ["pointer"]);
    },
    get stringGetLength() {
      return r("il2cpp_string_length", "int32", ["pointer"]);
    },
    get stringNew() {
      return r("il2cpp_string_new", "pointer", ["pointer"]);
    },
    get valueTypeBox() {
      return r("il2cpp_value_box", "pointer", ["pointer", "pointer"]);
    },
    get threadAttach() {
      return r("il2cpp_thread_attach", "pointer", ["pointer"]);
    },
    get threadDetach() {
      return r("il2cpp_thread_detach", "void", ["pointer"]);
    },
    get threadGetAttachedThreads() {
      return r("il2cpp_thread_get_all_attached_threads", "pointer", ["pointer"]);
    },
    get threadGetCurrent() {
      return r("il2cpp_thread_current", "pointer", []);
    },
    get threadIsVm() {
      return r("il2cpp_is_vm_thread", "bool", ["pointer"]);
    },
    get typeEquals() {
      return r("il2cpp_type_equals", "bool", ["pointer", "pointer"]);
    },
    get typeGetClass() {
      return r("il2cpp_class_from_type", "pointer", ["pointer"]);
    },
    get typeGetName() {
      return r("il2cpp_type_get_name", "pointer", ["pointer"]);
    },
    get typeGetObject() {
      return r("il2cpp_type_get_object", "pointer", ["pointer"]);
    },
    get typeGetTypeEnum() {
      return r("il2cpp_type_get_type", "int", ["pointer"]);
    }
  };
  decorate(Il2Cpp3.exports, lazy);
  getter(Il2Cpp3, "memorySnapshotExports", () => new CModule("#include <stdint.h>\n#include <string.h>\n\ntypedef struct Il2CppManagedMemorySnapshot Il2CppManagedMemorySnapshot;\ntypedef struct Il2CppMetadataType Il2CppMetadataType;\n\nstruct Il2CppManagedMemorySnapshot\n{\n  struct Il2CppManagedHeap\n  {\n    uint32_t section_count;\n    void * sections;\n  } heap;\n  struct Il2CppStacks\n  {\n    uint32_t stack_count;\n    void * stacks;\n  } stacks;\n  struct Il2CppMetadataSnapshot\n  {\n    uint32_t type_count;\n    Il2CppMetadataType * types;\n  } metadata_snapshot;\n  struct Il2CppGCHandles\n  {\n    uint32_t tracked_object_count;\n    void ** pointers_to_objects;\n  } gc_handles;\n  struct Il2CppRuntimeInformation\n  {\n    uint32_t pointer_size;\n    uint32_t object_header_size;\n    uint32_t array_header_size;\n    uint32_t array_bounds_offset_in_header;\n    uint32_t array_size_offset_in_header;\n    uint32_t allocation_granularity;\n  } runtime_information;\n  void * additional_user_information;\n};\n\nstruct Il2CppMetadataType\n{\n  uint32_t flags;\n  void * fields;\n  uint32_t field_count;\n  uint32_t statics_size;\n  uint8_t * statics;\n  uint32_t base_or_element_type_index;\n  char * name;\n  const char * assembly_name;\n  uint64_t type_info_address;\n  uint32_t size;\n};\n\nuintptr_t\nil2cpp_memory_snapshot_get_classes (\n    const Il2CppManagedMemorySnapshot * snapshot, Il2CppMetadataType ** iter)\n{\n  const int zero = 0;\n  const void * null = 0;\n\n  if (iter != NULL && snapshot->metadata_snapshot.type_count > zero)\n  {\n    if (*iter == null)\n    {\n      *iter = snapshot->metadata_snapshot.types;\n      return (uintptr_t) (*iter)->type_info_address;\n    }\n    else\n    {\n      Il2CppMetadataType * metadata_type = *iter + 1;\n\n      if (metadata_type < snapshot->metadata_snapshot.types +\n                              snapshot->metadata_snapshot.type_count)\n      {\n        *iter = metadata_type;\n        return (uintptr_t) (*iter)->type_info_address;\n      }\n    }\n  }\n  return 0;\n}\n\nvoid **\nil2cpp_memory_snapshot_get_objects (\n    const Il2CppManagedMemorySnapshot * snapshot, uint32_t * size)\n{\n  *size = snapshot->gc_handles.tracked_object_count;\n  return snapshot->gc_handles.pointers_to_objects;\n}\n"), lazy);
  function r(exportName, retType, argTypes) {
    const handle = Il2Cpp3.$config.exports?.[exportName]?.() ?? Il2Cpp3.module.findExportByName(exportName) ?? Il2Cpp3.memorySnapshotExports[exportName];
    const target = new NativeFunction(handle ?? NULL, retType, argTypes);
    return target.isNull() ? new Proxy(target, {
      get(value, name) {
        const property = value[name];
        return typeof property === "function" ? property.bind(value) : property;
      },
      apply() {
        if (handle == null) {
          raise(`couldn't resolve export ${exportName}`);
        } else if (handle.isNull()) {
          raise(`export ${exportName} points to NULL IL2CPP library has likely been stripped, obfuscated, or customized`);
        }
      }
    }) : target;
  }
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function is(klass) {
    return (element) => {
      if (element instanceof Il2Cpp3.Class) {
        return klass.isAssignableFrom(element);
      } else {
        return klass.isAssignableFrom(element.class);
      }
    };
  }
  Il2Cpp3.is = is;
  function isExactly(klass) {
    return (element) => {
      if (element instanceof Il2Cpp3.Class) {
        return element.equals(klass);
      } else {
        return element.class.equals(klass);
      }
    };
  }
  Il2Cpp3.isExactly = isExactly;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  Il2Cpp3.gc = {
    /**
     * Gets the heap size in bytes.
     */
    get heapSize() {
      return Il2Cpp3.exports.gcGetHeapSize();
    },
    /**
     * Determines whether the garbage collector is enabled.
     */
    get isEnabled() {
      return !Il2Cpp3.exports.gcIsDisabled();
    },
    /**
     * Determines whether the garbage collector is incremental
     * ([source](https://docs.unity3d.com/Manual/performance-incremental-garbage-collection.html)).
     */
    get isIncremental() {
      return !!Il2Cpp3.exports.gcIsIncremental();
    },
    /**
     * Gets the number of nanoseconds the garbage collector can spend in a
     * collection step.
     */
    get maxTimeSlice() {
      return Il2Cpp3.exports.gcGetMaxTimeSlice();
    },
    /**
     * Gets the used heap size in bytes.
     */
    get usedHeapSize() {
      return Il2Cpp3.exports.gcGetUsedSize();
    },
    /**
     * Enables or disables the garbage collector.
     */
    set isEnabled(value) {
      value ? Il2Cpp3.exports.gcEnable() : Il2Cpp3.exports.gcDisable();
    },
    /**
     *  Sets the number of nanoseconds the garbage collector can spend in
     * a collection step.
     */
    set maxTimeSlice(nanoseconds) {
      Il2Cpp3.exports.gcSetMaxTimeSlice(nanoseconds);
    },
    /**
     * Returns the heap allocated objects of the specified class. \
     * This variant reads GC descriptors.
     */
    choose(klass) {
      const matches = [];
      const callback = (objects, size) => {
        for (let i = 0; i < size; i++) {
          matches.push(new Il2Cpp3.Object(objects.add(i * Process.pointerSize).readPointer()));
        }
      };
      const chooseCallback = new NativeCallback(callback, "void", ["pointer", "int", "pointer"]);
      if (Il2Cpp3.unityVersionIsBelow202120) {
        const onWorld = new NativeCallback(() => {
        }, "void", []);
        const state = Il2Cpp3.exports.livenessCalculationBegin(klass, 0, chooseCallback, NULL, onWorld, onWorld);
        Il2Cpp3.exports.livenessCalculationFromStatics(state);
        Il2Cpp3.exports.livenessCalculationEnd(state);
      } else {
        const realloc = (handle, size) => {
          if (!handle.isNull() && size.compare(0) == 0) {
            Il2Cpp3.free(handle);
            return NULL;
          } else {
            return Il2Cpp3.alloc(size);
          }
        };
        const reallocCallback = new NativeCallback(realloc, "pointer", ["pointer", "size_t", "pointer"]);
        this.stopWorld();
        const state = Il2Cpp3.exports.livenessAllocateStruct(klass, 0, chooseCallback, NULL, reallocCallback);
        Il2Cpp3.exports.livenessCalculationFromStatics(state);
        Il2Cpp3.exports.livenessFinalize(state);
        this.startWorld();
        Il2Cpp3.exports.livenessFreeStruct(state);
      }
      return matches;
    },
    /**
     * Forces a garbage collection of the specified generation.
     */
    collect(generation) {
      Il2Cpp3.exports.gcCollect(generation < 0 ? 0 : generation > 2 ? 2 : generation);
    },
    /**
     * Forces a garbage collection.
     */
    collectALittle() {
      Il2Cpp3.exports.gcCollectALittle();
    },
    /**
     *  Resumes all the previously stopped threads.
     */
    startWorld() {
      return Il2Cpp3.exports.gcStartWorld();
    },
    /**
     * Performs an incremental garbage collection.
     */
    startIncrementalCollection() {
      return Il2Cpp3.exports.gcStartIncrementalCollection();
    },
    /**
     * Stops all threads which may access the garbage collected heap, other
     * than the caller.
     */
    stopWorld() {
      return Il2Cpp3.exports.gcStopWorld();
    }
  };
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Android;
(function(Android2) {
  getter(Android2, "apiLevel", () => {
    const value = getProperty("ro.build.version.sdk");
    return value ? parseInt(value) : null;
  }, lazy);
  function getProperty(name) {
    const handle = Process.findModuleByName("libc.so")?.findExportByName("__system_property_get");
    if (handle) {
      const __system_property_get = new NativeFunction(handle, "void", ["pointer", "pointer"]);
      const value = Memory.alloc(92).writePointer(NULL);
      __system_property_get(Memory.allocUtf8String(name), value);
      return value.readCString() ?? void 0;
    }
  }
})(Android || (Android = {}));
function raise(message) {
  const error = new Error(message);
  error.name = "Il2CppError";
  error.stack = error.stack?.replace(/^(Il2Cpp)?Error/, "\x1B[0m\x1B[38;5;9mil2cpp\x1B[0m")?.replace(/\n    at (.+) \((.+):(.+)\)/, "\x1B[3m\x1B[2m")?.concat("\x1B[0m");
  throw error;
}
function warn(message) {
  globalThis.console.log(`\x1B[38;5;11mil2cpp\x1B[0m: ${message}`);
}
function ok(message) {
  globalThis.console.log(`\x1B[38;5;10mil2cpp\x1B[0m: ${message}`);
}
function inform(message) {
  globalThis.console.log(`\x1B[38;5;12mil2cpp\x1B[0m: ${message}`);
}
function decorate(target, decorator, descriptors = Object.getOwnPropertyDescriptors(target)) {
  for (const key in descriptors) {
    descriptors[key] = decorator(target, key, descriptors[key]);
  }
  Object.defineProperties(target, descriptors);
  return target;
}
function getter(target, key, get, decorator) {
  globalThis.Object.defineProperty(target, key, decorator?.(target, key, { get, configurable: true }) ?? { get, configurable: true });
}
function cyrb53(str) {
  let h1 = 3735928559;
  let h2 = 1103547991;
  for (let i = 0, ch; i < str.length; i++) {
    ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ h1 >>> 16, 2246822507);
  h1 ^= Math.imul(h2 ^ h2 >>> 13, 3266489909);
  h2 = Math.imul(h2 ^ h2 >>> 16, 2246822507);
  h2 ^= Math.imul(h1 ^ h1 >>> 13, 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}
function exportsHash(module) {
  return cyrb53(module.enumerateExports().sort((a, b) => a.name.localeCompare(b.name)).map((_) => _.name + _.address.sub(module.base)).join(""));
}
function lazy(_, propertyKey, descriptor) {
  const getter2 = descriptor.get;
  if (!getter2) {
    throw new Error("@lazy can only be applied to getter accessors");
  }
  descriptor.get = function() {
    const value = getter2.call(this);
    Object.defineProperty(this, propertyKey, {
      value,
      configurable: descriptor.configurable,
      enumerable: descriptor.enumerable,
      writable: false
    });
    return value;
  };
  return descriptor;
}
var NativeStruct = class {
  handle;
  constructor(handleOrWrapper) {
    if (handleOrWrapper instanceof NativePointer) {
      this.handle = handleOrWrapper;
    } else {
      this.handle = handleOrWrapper.handle;
    }
  }
  equals(other) {
    return this.handle.equals(other.handle);
  }
  isNull() {
    return this.handle.isNull();
  }
  asNullable() {
    return this.isNull() ? null : this;
  }
};
function addFlippedEntries(obj) {
  return Object.keys(obj).reduce((obj2, key) => (obj2[obj2[key]] = key, obj2), obj);
}
NativePointer.prototype.offsetOf = function(condition, depth) {
  depth ??= 512;
  for (let i = 0; depth > 0 ? i < depth : i < -depth; i++) {
    if (condition(depth > 0 ? this.add(i) : this.sub(i))) {
      return i;
    }
  }
  return null;
};
function readNativeIterator(block) {
  const array = [];
  const iterator = Memory.alloc(Process.pointerSize);
  let handle = block(iterator);
  while (!handle.isNull()) {
    array.push(handle);
    handle = block(iterator);
  }
  return array;
}
function readNativeList(block) {
  const lengthPointer = Memory.alloc(Process.pointerSize);
  const startPointer = block(lengthPointer);
  if (startPointer.isNull()) {
    return [];
  }
  const array = new Array(lengthPointer.readInt());
  for (let i = 0; i < array.length; i++) {
    array[i] = startPointer.add(i * Process.pointerSize).readPointer();
  }
  return array;
}
function recycle(Class) {
  return new Proxy(Class, {
    cache: /* @__PURE__ */ new Map(),
    construct(Target, argArray) {
      const handle = argArray[0].toUInt32();
      if (!this.cache.has(handle)) {
        this.cache.set(handle, new Target(argArray[0]));
      }
      return this.cache.get(handle);
    }
  });
}
var UnityVersion;
(function(UnityVersion2) {
  const pattern = /(6\d{3}|20\d{2}|\d)\.(\d)\.(\d{1,2})(?:[abcfp]|rc){0,2}\d?/;
  function find(string) {
    return string?.match(pattern)?.[0];
  }
  UnityVersion2.find = find;
  function gte(a, b) {
    return compare(a, b) >= 0;
  }
  UnityVersion2.gte = gte;
  function lt(a, b) {
    return compare(a, b) < 0;
  }
  UnityVersion2.lt = lt;
  function compare(a, b) {
    const aMatches = a.match(pattern);
    const bMatches = b.match(pattern);
    for (let i = 1; i <= 3; i++) {
      const a2 = Number(aMatches?.[i] ?? -1);
      const b2 = Number(bMatches?.[i] ?? -1);
      if (a2 > b2)
        return 1;
      else if (a2 < b2)
        return -1;
    }
    return 0;
  }
})(UnityVersion || (UnityVersion = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function alloc(size = Process.pointerSize) {
    return Il2Cpp3.exports.alloc(size);
  }
  Il2Cpp3.alloc = alloc;
  function free(pointer) {
    return Il2Cpp3.exports.free(pointer);
  }
  Il2Cpp3.free = free;
  function read(pointer, type) {
    switch (type.enumValue) {
      case Il2Cpp3.Type.Enum.BOOLEAN:
        return !!pointer.readS8();
      case Il2Cpp3.Type.Enum.BYTE:
        return pointer.readS8();
      case Il2Cpp3.Type.Enum.UBYTE:
        return pointer.readU8();
      case Il2Cpp3.Type.Enum.SHORT:
        return pointer.readS16();
      case Il2Cpp3.Type.Enum.USHORT:
        return pointer.readU16();
      case Il2Cpp3.Type.Enum.INT:
        return pointer.readS32();
      case Il2Cpp3.Type.Enum.UINT:
        return pointer.readU32();
      case Il2Cpp3.Type.Enum.CHAR:
        return pointer.readU16();
      case Il2Cpp3.Type.Enum.LONG:
        return pointer.readS64();
      case Il2Cpp3.Type.Enum.ULONG:
        return pointer.readU64();
      case Il2Cpp3.Type.Enum.FLOAT:
        return pointer.readFloat();
      case Il2Cpp3.Type.Enum.DOUBLE:
        return pointer.readDouble();
      case Il2Cpp3.Type.Enum.NINT:
      case Il2Cpp3.Type.Enum.NUINT:
        return pointer.readPointer();
      case Il2Cpp3.Type.Enum.POINTER:
        return new Il2Cpp3.Pointer(pointer.readPointer(), type.class.baseType);
      case Il2Cpp3.Type.Enum.VALUE_TYPE:
        return new Il2Cpp3.ValueType(pointer, type);
      case Il2Cpp3.Type.Enum.OBJECT:
      case Il2Cpp3.Type.Enum.CLASS:
        return new Il2Cpp3.Object(pointer.readPointer());
      case Il2Cpp3.Type.Enum.GENERIC_INSTANCE:
        return type.class.isValueType ? new Il2Cpp3.ValueType(pointer, type) : new Il2Cpp3.Object(pointer.readPointer());
      case Il2Cpp3.Type.Enum.STRING:
        return new Il2Cpp3.String(pointer.readPointer());
      case Il2Cpp3.Type.Enum.ARRAY:
      case Il2Cpp3.Type.Enum.NARRAY:
        return new Il2Cpp3.Array(pointer.readPointer());
    }
    raise(`couldn't read the value from ${pointer} using an unhandled or unknown type ${type.name} (${type.enumValue}), please file an issue`);
  }
  Il2Cpp3.read = read;
  function write(pointer, value, type) {
    switch (type.enumValue) {
      case Il2Cpp3.Type.Enum.BOOLEAN:
        return pointer.writeS8(+value);
      case Il2Cpp3.Type.Enum.BYTE:
        return pointer.writeS8(value);
      case Il2Cpp3.Type.Enum.UBYTE:
        return pointer.writeU8(value);
      case Il2Cpp3.Type.Enum.SHORT:
        return pointer.writeS16(value);
      case Il2Cpp3.Type.Enum.USHORT:
        return pointer.writeU16(value);
      case Il2Cpp3.Type.Enum.INT:
        return pointer.writeS32(value);
      case Il2Cpp3.Type.Enum.UINT:
        return pointer.writeU32(value);
      case Il2Cpp3.Type.Enum.CHAR:
        return pointer.writeU16(value);
      case Il2Cpp3.Type.Enum.LONG:
        return pointer.writeS64(value);
      case Il2Cpp3.Type.Enum.ULONG:
        return pointer.writeU64(value);
      case Il2Cpp3.Type.Enum.FLOAT:
        return pointer.writeFloat(value);
      case Il2Cpp3.Type.Enum.DOUBLE:
        return pointer.writeDouble(value);
      case Il2Cpp3.Type.Enum.NINT:
      case Il2Cpp3.Type.Enum.NUINT:
      case Il2Cpp3.Type.Enum.POINTER:
      case Il2Cpp3.Type.Enum.STRING:
      case Il2Cpp3.Type.Enum.ARRAY:
      case Il2Cpp3.Type.Enum.NARRAY:
        return pointer.writePointer(value);
      case Il2Cpp3.Type.Enum.VALUE_TYPE:
        return Memory.copy(pointer, value, type.class.valueTypeSize), pointer;
      case Il2Cpp3.Type.Enum.OBJECT:
      case Il2Cpp3.Type.Enum.CLASS:
      case Il2Cpp3.Type.Enum.GENERIC_INSTANCE:
        return value instanceof Il2Cpp3.ValueType ? (Memory.copy(pointer, value, type.class.valueTypeSize), pointer) : pointer.writePointer(value);
    }
    raise(`couldn't write value ${value} to ${pointer} using an unhandled or unknown type ${type.name} (${type.enumValue}), please file an issue`);
  }
  Il2Cpp3.write = write;
  function fromFridaValue(value, type) {
    if (globalThis.Array.isArray(value)) {
      const handle = Memory.alloc(type.class.valueTypeSize);
      const fields = type.class.fields.filter((_) => !_.isStatic);
      for (let i = 0; i < fields.length; i++) {
        const convertedValue = fromFridaValue(value[i], fields[i].type);
        write(handle.add(fields[i].offset).sub(Il2Cpp3.Object.headerSize), convertedValue, fields[i].type);
      }
      return new Il2Cpp3.ValueType(handle, type);
    } else if (value instanceof NativePointer) {
      if (type.isByReference) {
        return new Il2Cpp3.Reference(value, type);
      }
      switch (type.enumValue) {
        case Il2Cpp3.Type.Enum.POINTER:
          return new Il2Cpp3.Pointer(value, type.class.baseType);
        case Il2Cpp3.Type.Enum.STRING:
          return new Il2Cpp3.String(value);
        case Il2Cpp3.Type.Enum.CLASS:
        case Il2Cpp3.Type.Enum.GENERIC_INSTANCE:
        case Il2Cpp3.Type.Enum.OBJECT:
          return new Il2Cpp3.Object(value);
        case Il2Cpp3.Type.Enum.ARRAY:
        case Il2Cpp3.Type.Enum.NARRAY:
          return new Il2Cpp3.Array(value);
        default:
          return value;
      }
    } else if (type.enumValue == Il2Cpp3.Type.Enum.BOOLEAN) {
      return !!value;
    } else if (type.enumValue == Il2Cpp3.Type.Enum.VALUE_TYPE && type.class.isEnum) {
      return fromFridaValue([value], type);
    } else {
      return value;
    }
  }
  Il2Cpp3.fromFridaValue = fromFridaValue;
  function toFridaValue(value) {
    if (typeof value == "boolean") {
      return +value;
    } else if (value instanceof Il2Cpp3.ValueType) {
      if (value.type.class.isEnum) {
        return value.field("value__").value;
      } else {
        const _ = value.type.class.fields.filter((_2) => !_2.isStatic).map((_2) => toFridaValue(_2.bind(value).value));
        return _.length == 0 ? [0] : _;
      }
    } else {
      return value;
    }
  }
  Il2Cpp3.toFridaValue = toFridaValue;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  getter(Il2Cpp3, "module", () => {
    return tryModule() ?? raise("Could not find IL2CPP module");
  });
  async function initialize(blocking = false) {
    const module = tryModule() ?? await new Promise((resolve) => {
      const [moduleName, fallbackModuleName] = getExpectedModuleNames();
      const timeout = setTimeout(() => {
        warn(`after 10 seconds, IL2CPP module '${moduleName}' has not been loaded yet, is the app running?`);
      }, 1e4);
      const moduleObserver = Process.attachModuleObserver({
        onAdded(module2) {
          if (module2.name == moduleName || fallbackModuleName && module2.name == fallbackModuleName) {
            clearTimeout(timeout);
            setImmediate(() => {
              resolve(module2);
              moduleObserver.detach();
            });
          }
        }
      });
    });
    Reflect.defineProperty(Il2Cpp3, "module", { value: module });
    if (Il2Cpp3.exports.getCorlib().isNull()) {
      return await new Promise((resolve) => {
        const timeout = setTimeout(() => {
          if (!Il2Cpp3.exports.getCorlib().isNull()) {
            warn(`resuming execution despite IL2CPP initialization not being captured in time, please open an issue as this is suboptimal`);
            interceptor.detach();
            resolve(false);
          }
        }, 1e3);
        const interceptor = Interceptor.attach(Il2Cpp3.exports.initialize, {
          onEnter() {
            clearTimeout(timeout);
          },
          onLeave() {
            interceptor.detach();
            blocking ? resolve(true) : setImmediate(() => resolve(false));
          }
        });
      });
    }
    return false;
  }
  Il2Cpp3.initialize = initialize;
  function tryModule() {
    const [moduleName, fallback] = getExpectedModuleNames();
    return Process.findModuleByName(moduleName) ?? Process.findModuleByName(fallback ?? moduleName) ?? (Process.platform == "darwin" ? Process.findModuleByAddress(DebugSymbol.fromName("il2cpp_init").address) : void 0) ?? void 0;
  }
  function getExpectedModuleNames() {
    if (Il2Cpp3.$config.moduleName) {
      return [Il2Cpp3.$config.moduleName];
    }
    switch (Process.platform) {
      case "linux":
        return [Android.apiLevel ? "libil2cpp.so" : "GameAssembly.so"];
      case "windows":
        return ["GameAssembly.dll"];
      case "darwin":
        return ["UnityFramework", "GameAssembly.dylib"];
    }
    raise(`${Process.platform} is not supported yet`);
  }
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function nullable(valueOrNull, klass) {
    const actualClass = typeof valueOrNull == "boolean" ? Il2Cpp3.corlib.class("System.Boolean") : typeof valueOrNull == "number" ? klass ?? Il2Cpp3.corlib.class("System.Int32") : valueOrNull instanceof Int64 ? Il2Cpp3.corlib.class("System.Int64") : valueOrNull instanceof UInt64 ? Il2Cpp3.corlib.class("System.UInt64") : valueOrNull instanceof NativePointer ? klass ?? Il2Cpp3.corlib.class("System.IntPtr") : valueOrNull instanceof Il2Cpp3.ValueType ? valueOrNull.type.class : klass ?? raise(`A class must be specified when constructing a nullable for value '${valueOrNull}'`);
    if (actualClass.isValueType == false) {
      raise(`Cannot create nullable value type out of a reference type '${actualClass.type.name}'`);
    }
    const inflatedClass = Il2Cpp3.corlib.class("System.Nullable`1").inflate(actualClass);
    const struct = new Il2Cpp3.ValueType(Memory.alloc(inflatedClass.valueTypeSize), inflatedClass.type);
    (struct.tryField("hasValue") ?? struct.field("has_value")).value = valueOrNull != null;
    if (valueOrNull != null) {
      struct.field("value").value = valueOrNull;
    }
    return struct;
  }
  Il2Cpp3.nullable = nullable;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  async function perform(block, flag = "bind") {
    let attachedThread = null;
    try {
      const isInMainThread = await Il2Cpp3.initialize(flag == "main");
      if (flag == "main" && !isInMainThread) {
        return perform(() => Il2Cpp3.mainThread.schedule(block), "free");
      }
      if (Il2Cpp3.currentThread == null) {
        attachedThread = Il2Cpp3.domain.attach();
      }
      if (flag == "bind" && attachedThread != null) {
        Script.bindWeak(globalThis, () => attachedThread?.detach());
      }
      const result = block();
      return result instanceof Promise ? await result : result;
    } catch (error) {
      Script.nextTick((_) => {
        throw _;
      }, error);
      return Promise.reject(error);
    } finally {
      if (flag == "free" && attachedThread != null) {
        attachedThread.detach();
      }
    }
  }
  Il2Cpp3.perform = perform;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Tracer {
    /** @internal */
    #state = {
      depth: 0,
      buffer: [],
      history: /* @__PURE__ */ new Set(),
      flush: () => {
        if (this.#state.depth == 0) {
          const message = `
${this.#state.buffer.join("\n")}
`;
          if (this.#verbose) {
            inform(message);
          } else {
            const hash = cyrb53(message);
            if (!this.#state.history.has(hash)) {
              this.#state.history.add(hash);
              inform(message);
            }
          }
          this.#state.buffer.length = 0;
        }
      }
    };
    /** @internal */
    #threadId = Il2Cpp3.mainThread.id;
    /** @internal */
    #verbose = false;
    /** @internal */
    #applier;
    /** @internal */
    #targets = [];
    /** @internal */
    #domain;
    /** @internal */
    #assemblies;
    /** @internal */
    #classes;
    /** @internal */
    #methods;
    /** @internal */
    #assemblyFilter;
    /** @internal */
    #classFilter;
    /** @internal */
    #methodFilter;
    /** @internal */
    #parameterFilter;
    constructor(applier) {
      this.#applier = applier;
    }
    /** */
    thread(thread) {
      this.#threadId = thread.id;
      return this;
    }
    /** Determines whether print duplicate logs. */
    verbose(value) {
      this.#verbose = value;
      return this;
    }
    /** Sets the application domain as the place where to find the target methods. */
    domain() {
      this.#domain = Il2Cpp3.domain;
      return this;
    }
    /** Sets the passed `assemblies` as the place where to find the target methods. */
    assemblies(...assemblies) {
      this.#assemblies = assemblies;
      return this;
    }
    /** Sets the passed `classes` as the place where to find the target methods. */
    classes(...classes) {
      this.#classes = classes;
      return this;
    }
    /** Sets the passed `methods` as the target methods. */
    methods(...methods) {
      this.#methods = methods;
      return this;
    }
    /** Filters the assemblies where to find the target methods. */
    filterAssemblies(filter) {
      this.#assemblyFilter = filter;
      return this;
    }
    /** Filters the classes where to find the target methods. */
    filterClasses(filter) {
      this.#classFilter = filter;
      return this;
    }
    /** Filters the target methods. */
    filterMethods(filter) {
      this.#methodFilter = filter;
      return this;
    }
    /** Filters the target methods. */
    filterParameters(filter) {
      this.#parameterFilter = filter;
      return this;
    }
    /** Commits the current changes by finding the target methods. */
    and() {
      const filterMethod = (method) => {
        if (this.#parameterFilter == void 0) {
          this.#targets.push(method);
          return;
        }
        for (const parameter of method.parameters) {
          if (this.#parameterFilter(parameter)) {
            this.#targets.push(method);
            break;
          }
        }
      };
      const filterMethods = (values) => {
        for (const method of values) {
          filterMethod(method);
        }
      };
      const filterClass = (klass) => {
        if (this.#methodFilter == void 0) {
          filterMethods(klass.methods);
          return;
        }
        for (const method of klass.methods) {
          if (this.#methodFilter(method)) {
            filterMethod(method);
          }
        }
      };
      const filterClasses = (values) => {
        for (const klass of values) {
          filterClass(klass);
        }
      };
      const filterAssembly = (assembly) => {
        if (this.#classFilter == void 0) {
          filterClasses(assembly.image.classes);
          return;
        }
        for (const klass of assembly.image.classes) {
          if (this.#classFilter(klass)) {
            filterClass(klass);
          }
        }
      };
      const filterAssemblies = (assemblies) => {
        for (const assembly of assemblies) {
          filterAssembly(assembly);
        }
      };
      const filterDomain = (domain) => {
        if (this.#assemblyFilter == void 0) {
          filterAssemblies(domain.assemblies);
          return;
        }
        for (const assembly of domain.assemblies) {
          if (this.#assemblyFilter(assembly)) {
            filterAssembly(assembly);
          }
        }
      };
      this.#methods ? filterMethods(this.#methods) : this.#classes ? filterClasses(this.#classes) : this.#assemblies ? filterAssemblies(this.#assemblies) : this.#domain ? filterDomain(this.#domain) : void 0;
      this.#assemblies = void 0;
      this.#classes = void 0;
      this.#methods = void 0;
      this.#assemblyFilter = void 0;
      this.#classFilter = void 0;
      this.#methodFilter = void 0;
      this.#parameterFilter = void 0;
      return this;
    }
    /** Starts tracing. */
    attach() {
      for (const target of this.#targets) {
        if (!target.virtualAddress.isNull()) {
          try {
            this.#applier(target, this.#state, this.#threadId);
          } catch (e) {
            switch (e.message) {
              case /unable to intercept function at \w+; please file a bug/.exec(e.message)?.input:
              case "already replaced this function":
                break;
              default:
                throw e;
            }
          }
        }
      }
    }
  }
  Il2Cpp3.Tracer = Tracer;
  function trace(parameters = false) {
    const applier = () => (method, state, threadId) => {
      const paddedVirtualAddress = method.relativeVirtualAddress.toString(16).padStart(8, "0");
      Interceptor.attach(method.virtualAddress, {
        onEnter() {
          if (this.threadId == threadId) {
            state.buffer.push(`\x1B[2m0x${paddedVirtualAddress}\x1B[0m ${`\u2502 `.repeat(state.depth++)}\u250C\u2500\x1B[35m${method.class.type.name}::\x1B[1m${method.name}\x1B[0m\x1B[0m`);
          }
        },
        onLeave() {
          if (this.threadId == threadId) {
            state.buffer.push(`\x1B[2m0x${paddedVirtualAddress}\x1B[0m ${`\u2502 `.repeat(--state.depth)}\u2514\u2500\x1B[33m${method.class.type.name}::\x1B[1m${method.name}\x1B[0m\x1B[0m`);
            state.flush();
          }
        }
      });
    };
    const applierWithParameters = () => (method, state, threadId) => {
      const paddedVirtualAddress = method.relativeVirtualAddress.toString(16).padStart(8, "0");
      const startIndex = +!method.isStatic | +Il2Cpp3.unityVersionIsBelow201830;
      const callback = function(...args) {
        if (this.threadId == threadId) {
          const thisParameter = method.isStatic ? void 0 : new Il2Cpp3.Parameter("this", -1, method.class.type);
          const parameters2 = thisParameter ? [thisParameter].concat(method.parameters) : method.parameters;
          state.buffer.push(`\x1B[2m0x${paddedVirtualAddress}\x1B[0m ${`\u2502 `.repeat(state.depth++)}\u250C\u2500\x1B[35m${method.class.type.name}::\x1B[1m${method.name}\x1B[0m\x1B[0m(${parameters2.map((e) => `\x1B[32m${e.name}\x1B[0m = \x1B[31m${Il2Cpp3.fromFridaValue(args[e.position + startIndex], e.type)}\x1B[0m`).join(", ")})`);
        }
        const returnValue = method.nativeFunction(...args);
        if (this.threadId == threadId) {
          state.buffer.push(`\x1B[2m0x${paddedVirtualAddress}\x1B[0m ${`\u2502 `.repeat(--state.depth)}\u2514\u2500\x1B[33m${method.class.type.name}::\x1B[1m${method.name}\x1B[0m\x1B[0m${returnValue == void 0 ? "" : ` = \x1B[36m${Il2Cpp3.fromFridaValue(returnValue, method.returnType)}`}\x1B[0m`);
          state.flush();
        }
        return returnValue;
      };
      method.revert();
      const nativeCallback = new NativeCallback(callback, method.returnType.fridaAlias, method.fridaSignature);
      Interceptor.replace(method.virtualAddress, nativeCallback);
    };
    return new Il2Cpp3.Tracer(parameters ? applierWithParameters() : applier());
  }
  Il2Cpp3.trace = trace;
  function backtrace(mode) {
    const methods = Il2Cpp3.domain.assemblies.flatMap((_) => _.image.classes.flatMap((_2) => _2.methods.filter((_3) => !_3.virtualAddress.isNull()))).sort((_, __) => _.virtualAddress.compare(__.virtualAddress));
    const searchInsert = (target) => {
      let left = 0;
      let right = methods.length - 1;
      while (left <= right) {
        const pivot = Math.floor((left + right) / 2);
        const comparison = methods[pivot].virtualAddress.compare(target);
        if (comparison == 0) {
          return methods[pivot];
        } else if (comparison > 0) {
          right = pivot - 1;
        } else {
          left = pivot + 1;
        }
      }
      return methods[right];
    };
    const applier = () => (method, state, threadId) => {
      Interceptor.attach(method.virtualAddress, function() {
        if (this.threadId == threadId) {
          const handles = globalThis.Thread.backtrace(this.context, mode);
          handles.unshift(method.virtualAddress);
          for (const handle of handles) {
            if (handle.compare(Il2Cpp3.module.base) > 0 && handle.compare(Il2Cpp3.module.base.add(Il2Cpp3.module.size)) < 0) {
              const method2 = searchInsert(handle);
              if (method2) {
                const offset = handle.sub(method2.virtualAddress);
                if (offset.compare(4095) < 0) {
                  state.buffer.push(`\x1B[2m0x${method2.relativeVirtualAddress.toString(16).padStart(8, "0")}\x1B[0m\x1B[2m+0x${offset.toString(16).padStart(3, `0`)}\x1B[0m ${method2.class.type.name}::\x1B[1m${method2.name}\x1B[0m`);
                }
              }
            }
          }
          state.flush();
        }
      });
    };
    return new Il2Cpp3.Tracer(applier());
  }
  Il2Cpp3.backtrace = backtrace;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Array2 extends NativeStruct {
    /** Gets the Il2CppArray struct size, possibly equal to `Process.pointerSize * 4`. */
    static get headerSize() {
      return Il2Cpp3.corlib.class("System.Array").instanceSize;
    }
    /** @internal Gets a pointer to the first element of the current array. */
    get elements() {
      const array2 = Il2Cpp3.string("vfsfitvnm").object.method("ToCharArray", 0).invoke();
      const offset = Memory.scanSync(array2.handle, 255, "76 00 66 00 73 00 66 00 69 00 74 00 76 00 6e 00 6d 00")[0]?.address?.sub(array2.handle) ?? raise("couldn't find the elements offset in the native array struct");
      getter(Il2Cpp3.Array.prototype, "elements", function() {
        return new Il2Cpp3.Pointer(this.handle.add(offset), this.elementType);
      }, lazy);
      return this.elements;
    }
    /** Gets the size of the object encompassed by the current array. */
    get elementSize() {
      return this.elementType.class.arrayElementSize;
    }
    /** Gets the type of the object encompassed by the current array. */
    get elementType() {
      return this.object.class.type.class.baseType;
    }
    /** Gets the total number of elements in all the dimensions of the current array. */
    get length() {
      return Il2Cpp3.exports.arrayGetLength(this);
    }
    /** Gets the encompassing object of the current array. */
    get object() {
      return new Il2Cpp3.Object(this);
    }
    /** Gets the element at the specified index of the current array. */
    get(index) {
      if (index < 0 || index >= this.length) {
        raise(`cannot get element at index ${index} as the array length is ${this.length}`);
      }
      return this.elements.get(index);
    }
    /** Sets the element at the specified index of the current array. */
    set(index, value) {
      if (index < 0 || index >= this.length) {
        raise(`cannot set element at index ${index} as the array length is ${this.length}`);
      }
      this.elements.set(index, value);
    }
    /** */
    toString() {
      return this.isNull() ? "null" : `[${this.elements.read(this.length, 0)}]`;
    }
    /** Iterable. */
    *[Symbol.iterator]() {
      for (let i = 0; i < this.length; i++) {
        yield this.elements.get(i);
      }
    }
  }
  __decorate([
    lazy
  ], Array2.prototype, "elementSize", null);
  __decorate([
    lazy
  ], Array2.prototype, "elementType", null);
  __decorate([
    lazy
  ], Array2.prototype, "length", null);
  __decorate([
    lazy
  ], Array2.prototype, "object", null);
  __decorate([
    lazy
  ], Array2, "headerSize", null);
  Il2Cpp3.Array = Array2;
  function array(klass, lengthOrElements) {
    const length = typeof lengthOrElements == "number" ? lengthOrElements : lengthOrElements.length;
    const array2 = new Il2Cpp3.Array(Il2Cpp3.exports.arrayNew(klass, length));
    if (globalThis.Array.isArray(lengthOrElements)) {
      array2.elements.write(lengthOrElements);
    }
    return array2;
  }
  Il2Cpp3.array = array;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  let Assembly = class Assembly extends NativeStruct {
    /** Gets the image of this assembly. */
    get image() {
      if (Il2Cpp3.exports.assemblyGetImage.isNull()) {
        const runtimeModule = this.object.tryMethod("GetType", 1)?.invoke(Il2Cpp3.string("<Module>"))?.asNullable()?.tryMethod("get_Module")?.invoke() ?? this.object.tryMethod("GetModules", 1)?.invoke(false)?.get(0) ?? raise(`couldn't find the runtime module object of assembly ${this.name}`);
        return new Il2Cpp3.Image(runtimeModule.field("_impl").value);
      }
      return new Il2Cpp3.Image(Il2Cpp3.exports.assemblyGetImage(this));
    }
    /** Gets the name of this assembly. */
    get name() {
      return this.image.name.replace(".dll", "");
    }
    /** Gets the encompassing object of the current assembly. */
    get object() {
      for (const _ of Il2Cpp3.domain.object.method("GetAssemblies", 1).invoke(false)) {
        if (_.field("_mono_assembly").value.equals(this)) {
          return _;
        }
      }
      raise("couldn't find the object of the native assembly struct");
    }
  };
  __decorate([
    lazy
  ], Assembly.prototype, "name", null);
  __decorate([
    lazy
  ], Assembly.prototype, "object", null);
  Assembly = __decorate([
    recycle
  ], Assembly);
  Il2Cpp3.Assembly = Assembly;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  let Class = class Class extends NativeStruct {
    /** Gets the actual size of the instance of the current class. */
    get actualInstanceSize() {
      const SystemString = Il2Cpp3.corlib.class("System.String");
      const offset = SystemString.handle.offsetOf((_) => _.readInt() == SystemString.instanceSize - 2) ?? raise("couldn't find the actual instance size offset in the native class struct");
      getter(Il2Cpp3.Class.prototype, "actualInstanceSize", function() {
        return this.handle.add(offset).readS32();
      }, lazy);
      return this.actualInstanceSize;
    }
    /** Gets the array class which encompass the current class. */
    get arrayClass() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.classGetArrayClass(this, 1));
    }
    /** Gets the size of the object encompassed by the current array class. */
    get arrayElementSize() {
      return Il2Cpp3.exports.classGetArrayElementSize(this);
    }
    /** Gets the name of the assembly in which the current class is defined. */
    get assemblyName() {
      return Il2Cpp3.exports.classGetAssemblyName(this).readUtf8String().replace(".dll", "");
    }
    /** Gets the class that declares the current nested class. */
    get declaringClass() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.classGetDeclaringType(this)).asNullable();
    }
    /** Gets the encompassed type of this array, reference, pointer or enum type. */
    get baseType() {
      return new Il2Cpp3.Type(Il2Cpp3.exports.classGetBaseType(this)).asNullable();
    }
    /** Gets the class of the object encompassed or referred to by the current array, pointer or reference class. */
    get elementClass() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.classGetElementClass(this)).asNullable();
    }
    /** Gets the fields of the current class. */
    get fields() {
      return readNativeIterator((_) => Il2Cpp3.exports.classGetFields(this, _)).map((_) => new Il2Cpp3.Field(_));
    }
    /** Gets the flags of the current class. */
    get flags() {
      return Il2Cpp3.exports.classGetFlags(this);
    }
    /** Gets the full name (namespace + name) of the current class. */
    get fullName() {
      return this.namespace ? `${this.namespace}.${this.name}` : this.name;
    }
    /** Gets the generic class of the current class if the current class is inflated. */
    get genericClass() {
      const klass = this.image.tryClass(this.fullName)?.asNullable();
      return klass?.equals(this) ? null : klass ?? null;
    }
    /** Gets the generics parameters of this generic class. */
    get generics() {
      if (!this.isGeneric && !this.isInflated) {
        return [];
      }
      const types = this.type.object.method("GetGenericArguments").invoke();
      return globalThis.Array.from(types).map((_) => new Il2Cpp3.Class(Il2Cpp3.exports.classFromObject(_)));
    }
    /** Determines whether the GC has tracking references to the current class instances. */
    get hasReferences() {
      return !!Il2Cpp3.exports.classHasReferences(this);
    }
    /** Determines whether ther current class has a valid static constructor. */
    get hasStaticConstructor() {
      const staticConstructor = this.tryMethod(".cctor");
      return staticConstructor != null && !staticConstructor.virtualAddress.isNull();
    }
    /** Gets the image in which the current class is defined. */
    get image() {
      return new Il2Cpp3.Image(Il2Cpp3.exports.classGetImage(this));
    }
    /** Gets the size of the instance of the current class. */
    get instanceSize() {
      return Il2Cpp3.exports.classGetInstanceSize(this);
    }
    /** Determines whether the current class is abstract. */
    get isAbstract() {
      return !!Il2Cpp3.exports.classIsAbstract(this);
    }
    /** Determines whether the current class is blittable. */
    get isBlittable() {
      return !!Il2Cpp3.exports.classIsBlittable(this);
    }
    /** Determines whether the current class is an enumeration. */
    get isEnum() {
      return !!Il2Cpp3.exports.classIsEnum(this);
    }
    /** Determines whether the current class is a generic one. */
    get isGeneric() {
      return !!Il2Cpp3.exports.classIsGeneric(this);
    }
    /** Determines whether the current class is inflated. */
    get isInflated() {
      return !!Il2Cpp3.exports.classIsInflated(this);
    }
    /** Determines whether the current class is an interface. */
    get isInterface() {
      return !!Il2Cpp3.exports.classIsInterface(this);
    }
    /** Determines whether the current class is a struct. */
    get isStruct() {
      return this.isValueType && !this.isEnum;
    }
    /** Determines whether the current class is a value type. */
    get isValueType() {
      return !!Il2Cpp3.exports.classIsValueType(this);
    }
    /** Gets the interfaces implemented or inherited by the current class. */
    get interfaces() {
      return readNativeIterator((_) => Il2Cpp3.exports.classGetInterfaces(this, _)).map((_) => new Il2Cpp3.Class(_));
    }
    /** Gets the methods implemented by the current class. */
    get methods() {
      return readNativeIterator((_) => Il2Cpp3.exports.classGetMethods(this, _)).map((_) => new Il2Cpp3.Method(_));
    }
    /** Gets the name of the current class. */
    get name() {
      return Il2Cpp3.exports.classGetName(this).readUtf8String();
    }
    /** Gets the namespace of the current class. */
    get namespace() {
      return Il2Cpp3.exports.classGetNamespace(this).readUtf8String() || void 0;
    }
    /** Gets the classes nested inside the current class. */
    get nestedClasses() {
      return readNativeIterator((_) => Il2Cpp3.exports.classGetNestedClasses(this, _)).map((_) => new Il2Cpp3.Class(_));
    }
    /** Gets the class from which the current class directly inherits. */
    get parent() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.classGetParent(this)).asNullable();
    }
    /** Gets the pointer class of the current class. */
    get pointerClass() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.classFromObject(this.type.object.method("MakePointerType").invoke()));
    }
    /** Gets the rank (number of dimensions) of the current array class. */
    get rank() {
      let rank = 0;
      const name = this.name;
      for (let i = this.name.length - 1; i > 0; i--) {
        const c = name[i];
        if (c == "]")
          rank++;
        else if (c == "[" || rank == 0)
          break;
        else if (c == ",")
          rank++;
        else
          break;
      }
      return rank;
    }
    /** Gets a pointer to the static fields of the current class. */
    get staticFieldsData() {
      return Il2Cpp3.exports.classGetStaticFieldData(this);
    }
    /** Gets the size of the instance - as a value type - of the current class. */
    get valueTypeSize() {
      return Il2Cpp3.exports.classGetValueTypeSize(this, NULL);
    }
    /** Gets the type of the current class. */
    get type() {
      return new Il2Cpp3.Type(Il2Cpp3.exports.classGetType(this));
    }
    /** Allocates a new object of the current class. */
    alloc() {
      return new Il2Cpp3.Object(Il2Cpp3.exports.objectNew(this));
    }
    /** Gets the field identified by the given name. */
    field(name) {
      return this.tryField(name) ?? raise(`couldn't find field ${name} in class ${this.type.name}`);
    }
    /** Gets the hierarchy of the current class. */
    *hierarchy(options) {
      let klass = options?.includeCurrent ?? true ? this : this.parent;
      while (klass) {
        yield klass;
        klass = klass.parent;
      }
    }
    /** Builds a generic instance of the current generic class. */
    inflate(...classes) {
      if (!this.isGeneric) {
        raise(`cannot inflate class ${this.type.name} as it has no generic parameters`);
      }
      if (this.generics.length != classes.length) {
        raise(`cannot inflate class ${this.type.name} as it needs ${this.generics.length} generic parameter(s), not ${classes.length}`);
      }
      const types = classes.map((_) => _.type.object);
      const typeArray = Il2Cpp3.array(Il2Cpp3.corlib.class("System.Type"), types);
      const inflatedType = this.type.object.method("MakeGenericType", 1).invoke(typeArray);
      return new Il2Cpp3.Class(Il2Cpp3.exports.classFromObject(inflatedType));
    }
    /** Calls the static constructor of the current class. */
    initialize() {
      Il2Cpp3.exports.classInitialize(this);
      return this;
    }
    /** Determines whether an instance of `other` class can be assigned to a variable of the current type. */
    isAssignableFrom(other) {
      return !!Il2Cpp3.exports.classIsAssignableFrom(this, other);
    }
    /** Determines whether the current class derives from `other` class. */
    isSubclassOf(other, checkInterfaces) {
      return !!Il2Cpp3.exports.classIsSubclassOf(this, other, +checkInterfaces);
    }
    /** Gets the method identified by the given name and parameter count. */
    method(name, parameterCount = -1) {
      return this.tryMethod(name, parameterCount) ?? raise(`couldn't find method ${name} in class ${this.type.name}`);
    }
    /** Gets the nested class with the given name. */
    nested(name) {
      return this.tryNested(name) ?? raise(`couldn't find nested class ${name} in class ${this.type.name}`);
    }
    /** Allocates a new object of the current class and calls its default constructor. */
    new() {
      const object = this.alloc();
      const exceptionArray = Memory.alloc(Process.pointerSize);
      Il2Cpp3.exports.objectInitialize(object, exceptionArray);
      const exception = exceptionArray.readPointer();
      if (!exception.isNull()) {
        raise(new Il2Cpp3.Object(exception).toString());
      }
      return object;
    }
    /** Gets the field with the given name. */
    tryField(name) {
      return new Il2Cpp3.Field(Il2Cpp3.exports.classGetFieldFromName(this, Memory.allocUtf8String(name))).asNullable();
    }
    /** Gets the method with the given name and parameter count. */
    tryMethod(name, parameterCount = -1) {
      return new Il2Cpp3.Method(Il2Cpp3.exports.classGetMethodFromName(this, Memory.allocUtf8String(name), parameterCount)).asNullable();
    }
    /** Gets the nested class with the given name. */
    tryNested(name) {
      return this.nestedClasses.find((_) => _.name == name);
    }
    /** */
    toString() {
      const inherited = [this.parent].concat(this.interfaces);
      return `// ${this.assemblyName}
${this.isEnum ? `enum` : this.isStruct ? `struct` : this.isInterface ? `interface` : `class`} ${this.type.name}${inherited ? ` : ${inherited.map((_) => _?.type.name).join(`, `)}` : ``}
{
    ${this.fields.join(`
    `)}
    ${this.methods.join(`
    `)}
}`;
    }
    /** Executes a callback for every defined class. */
    static enumerate(block) {
      const callback = new NativeCallback((_) => block(new Il2Cpp3.Class(_)), "void", ["pointer", "pointer"]);
      return Il2Cpp3.exports.classForEach(callback, NULL);
    }
  };
  __decorate([
    lazy
  ], Class.prototype, "arrayClass", null);
  __decorate([
    lazy
  ], Class.prototype, "arrayElementSize", null);
  __decorate([
    lazy
  ], Class.prototype, "assemblyName", null);
  __decorate([
    lazy
  ], Class.prototype, "declaringClass", null);
  __decorate([
    lazy
  ], Class.prototype, "baseType", null);
  __decorate([
    lazy
  ], Class.prototype, "elementClass", null);
  __decorate([
    lazy
  ], Class.prototype, "fields", null);
  __decorate([
    lazy
  ], Class.prototype, "flags", null);
  __decorate([
    lazy
  ], Class.prototype, "fullName", null);
  __decorate([
    lazy
  ], Class.prototype, "generics", null);
  __decorate([
    lazy
  ], Class.prototype, "hasReferences", null);
  __decorate([
    lazy
  ], Class.prototype, "hasStaticConstructor", null);
  __decorate([
    lazy
  ], Class.prototype, "image", null);
  __decorate([
    lazy
  ], Class.prototype, "instanceSize", null);
  __decorate([
    lazy
  ], Class.prototype, "isAbstract", null);
  __decorate([
    lazy
  ], Class.prototype, "isBlittable", null);
  __decorate([
    lazy
  ], Class.prototype, "isEnum", null);
  __decorate([
    lazy
  ], Class.prototype, "isGeneric", null);
  __decorate([
    lazy
  ], Class.prototype, "isInflated", null);
  __decorate([
    lazy
  ], Class.prototype, "isInterface", null);
  __decorate([
    lazy
  ], Class.prototype, "isValueType", null);
  __decorate([
    lazy
  ], Class.prototype, "interfaces", null);
  __decorate([
    lazy
  ], Class.prototype, "methods", null);
  __decorate([
    lazy
  ], Class.prototype, "name", null);
  __decorate([
    lazy
  ], Class.prototype, "namespace", null);
  __decorate([
    lazy
  ], Class.prototype, "nestedClasses", null);
  __decorate([
    lazy
  ], Class.prototype, "parent", null);
  __decorate([
    lazy
  ], Class.prototype, "pointerClass", null);
  __decorate([
    lazy
  ], Class.prototype, "rank", null);
  __decorate([
    lazy
  ], Class.prototype, "staticFieldsData", null);
  __decorate([
    lazy
  ], Class.prototype, "valueTypeSize", null);
  __decorate([
    lazy
  ], Class.prototype, "type", null);
  Class = __decorate([
    recycle
  ], Class);
  Il2Cpp3.Class = Class;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  function delegate(klass, block) {
    const SystemDelegate = Il2Cpp3.corlib.class("System.Delegate");
    const SystemMulticastDelegate = Il2Cpp3.corlib.class("System.MulticastDelegate");
    if (!SystemDelegate.isAssignableFrom(klass)) {
      raise(`cannot create a delegate for ${klass.type.name} as it's a non-delegate class`);
    }
    if (klass.equals(SystemDelegate) || klass.equals(SystemMulticastDelegate)) {
      raise(`cannot create a delegate for neither ${SystemDelegate.type.name} nor ${SystemMulticastDelegate.type.name}, use a subclass instead`);
    }
    const delegate2 = klass.alloc();
    const key = delegate2.handle.toString();
    const Invoke = delegate2.tryMethod("Invoke") ?? raise(`cannot create a delegate for ${klass.type.name}, there is no Invoke method`);
    delegate2.method(".ctor").invoke(delegate2, Invoke.handle);
    const callback = Invoke.wrap(block);
    delegate2.field("method_ptr").value = callback;
    delegate2.field("invoke_impl").value = callback;
    Il2Cpp3._callbacksToKeepAlive[key] = callback;
    return delegate2;
  }
  Il2Cpp3.delegate = delegate;
  Il2Cpp3._callbacksToKeepAlive = {};
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  let Domain = class Domain extends NativeStruct {
    /** Gets the assemblies that have been loaded into the execution context of the application domain. */
    get assemblies() {
      let handles = readNativeList((_) => Il2Cpp3.exports.domainGetAssemblies(this, _));
      if (handles.length == 0) {
        const assemblyObjects = this.object.method("GetAssemblies").overload().invoke();
        handles = globalThis.Array.from(assemblyObjects).map((_) => _.field("_mono_assembly").value);
      }
      return handles.map((_) => new Il2Cpp3.Assembly(_));
    }
    /** Gets the encompassing object of the application domain. */
    get object() {
      return Il2Cpp3.corlib.class("System.AppDomain").method("get_CurrentDomain").invoke();
    }
    /** Opens and loads the assembly with the given name. */
    assembly(name) {
      return this.tryAssembly(name) ?? raise(`couldn't find assembly ${name}`);
    }
    /** Attached a new thread to the application domain. */
    attach() {
      return new Il2Cpp3.Thread(Il2Cpp3.exports.threadAttach(this));
    }
    /** Opens and loads the assembly with the given name. */
    tryAssembly(name) {
      return new Il2Cpp3.Assembly(Il2Cpp3.exports.domainGetAssemblyFromName(this, Memory.allocUtf8String(name))).asNullable();
    }
  };
  __decorate([
    lazy
  ], Domain.prototype, "assemblies", null);
  __decorate([
    lazy
  ], Domain.prototype, "object", null);
  Domain = __decorate([
    recycle
  ], Domain);
  Il2Cpp3.Domain = Domain;
  getter(Il2Cpp3, "domain", () => {
    return new Il2Cpp3.Domain(Il2Cpp3.exports.domainGet());
  }, lazy);
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Field extends NativeStruct {
    /** Gets the class in which this field is defined. */
    get class() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.fieldGetClass(this));
    }
    /** Gets the flags of the current field. */
    get flags() {
      return Il2Cpp3.exports.fieldGetFlags(this);
    }
    /** Determines whether this field value is known at compile time. */
    get isLiteral() {
      return (this.flags & 64) != 0;
    }
    /** Determines whether this field is static. */
    get isStatic() {
      return (this.flags & 16) != 0;
    }
    /** Determines whether this field is thread static. */
    get isThreadStatic() {
      const offset = Il2Cpp3.corlib.class("System.AppDomain").field("type_resolve_in_progress").offset;
      getter(Il2Cpp3.Field.prototype, "isThreadStatic", function() {
        return this.offset == offset;
      }, lazy);
      return this.isThreadStatic;
    }
    /** Gets the access modifier of this field. */
    get modifier() {
      switch (this.flags & 7) {
        case 1:
          return "private";
        case 2:
          return "private protected";
        case 3:
          return "internal";
        case 4:
          return "protected";
        case 5:
          return "protected internal";
        case 6:
          return "public";
      }
    }
    /** Gets the name of this field. */
    get name() {
      return Il2Cpp3.exports.fieldGetName(this).readUtf8String();
    }
    /** Gets the offset of this field, calculated as the difference with its owner virtual address. */
    get offset() {
      return Il2Cpp3.exports.fieldGetOffset(this);
    }
    /** Gets the type of this field. */
    get type() {
      return new Il2Cpp3.Type(Il2Cpp3.exports.fieldGetType(this));
    }
    /** Gets the value of this field. */
    get value() {
      if (!this.isStatic) {
        raise(`cannot access instance field ${this.class.type.name}::${this.name} from a class, use an object instead`);
      }
      const handle = Memory.alloc(Process.pointerSize);
      Il2Cpp3.exports.fieldGetStaticValue(this.handle, handle);
      return Il2Cpp3.read(handle, this.type);
    }
    /** Sets the value of this field. Thread static or literal values cannot be altered yet. */
    set value(value) {
      if (!this.isStatic) {
        raise(`cannot access instance field ${this.class.type.name}::${this.name} from a class, use an object instead`);
      }
      if (this.isThreadStatic || this.isLiteral) {
        raise(`cannot write the value of field ${this.name} as it's thread static or literal`);
      }
      const handle = (
        // pointer-like values should be passed as-is, but boxed
        // value types (primitives included) must be unboxed first
        value instanceof Il2Cpp3.Object && this.type.class.isValueType ? value.unbox() : value instanceof NativeStruct ? value.handle : value instanceof NativePointer ? value : Il2Cpp3.write(Memory.alloc(this.type.class.valueTypeSize), value, this.type)
      );
      Il2Cpp3.exports.fieldSetStaticValue(this.handle, handle);
    }
    /** */
    toString() {
      return `${this.isThreadStatic ? `[ThreadStatic] ` : ``}${this.isStatic ? `static ` : ``}${this.type.name} ${this.name}${this.isLiteral ? ` = ${this.type.class.isEnum ? Il2Cpp3.read(this.value.handle, this.type.class.baseType) : this.value}` : ``};${this.isThreadStatic || this.isLiteral ? `` : ` // 0x${this.offset.toString(16)}`}`;
    }
    /**
     * @internal
     * Binds the current field to a {@link Il2Cpp.Object} or a
     * {@link Il2Cpp.ValueType} (also known as *instances*), so that it is
     * possible to retrieve its value - see {@link Il2Cpp.Field.value} for
     * details. \
     * Binding a static field is forbidden.
     */
    bind(instance) {
      if (this.isStatic) {
        raise(`cannot bind static field ${this.class.type.name}::${this.name} to an instance`);
      }
      const offset = this.offset - (instance instanceof Il2Cpp3.ValueType ? Il2Cpp3.Object.headerSize : 0);
      return new Proxy(this, {
        get(target, property) {
          if (property == "value") {
            return Il2Cpp3.read(instance.handle.add(offset), target.type);
          }
          return Reflect.get(target, property);
        },
        set(target, property, value) {
          if (property == "value") {
            Il2Cpp3.write(instance.handle.add(offset), value, target.type);
            return true;
          }
          return Reflect.set(target, property, value);
        }
      });
    }
  }
  __decorate([
    lazy
  ], Field.prototype, "class", null);
  __decorate([
    lazy
  ], Field.prototype, "flags", null);
  __decorate([
    lazy
  ], Field.prototype, "isLiteral", null);
  __decorate([
    lazy
  ], Field.prototype, "isStatic", null);
  __decorate([
    lazy
  ], Field.prototype, "isThreadStatic", null);
  __decorate([
    lazy
  ], Field.prototype, "modifier", null);
  __decorate([
    lazy
  ], Field.prototype, "name", null);
  __decorate([
    lazy
  ], Field.prototype, "offset", null);
  __decorate([
    lazy
  ], Field.prototype, "type", null);
  Il2Cpp3.Field = Field;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class GCHandle {
    handle;
    /** @internal */
    constructor(handle) {
      this.handle = handle;
    }
    /** Gets the object associated to this handle. */
    get target() {
      return new Il2Cpp3.Object(Il2Cpp3.exports.gcHandleGetTarget(this.handle)).asNullable();
    }
    /** Frees this handle. */
    free() {
      return Il2Cpp3.exports.gcHandleFree(this.handle);
    }
  }
  Il2Cpp3.GCHandle = GCHandle;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  let Image = class Image extends NativeStruct {
    /** Gets the assembly in which the current image is defined. */
    get assembly() {
      return new Il2Cpp3.Assembly(Il2Cpp3.exports.imageGetAssembly(this));
    }
    /** Gets the amount of classes defined in this image. */
    get classCount() {
      if (Il2Cpp3.unityVersionIsBelow201830) {
        return this.classes.length;
      } else {
        return Il2Cpp3.exports.imageGetClassCount(this);
      }
    }
    /** Gets the classes defined in this image. */
    get classes() {
      if (Il2Cpp3.unityVersionIsBelow201830) {
        const types = this.assembly.object.method("GetTypes").invoke(false);
        const classes = globalThis.Array.from(types, (_) => new Il2Cpp3.Class(Il2Cpp3.exports.classFromObject(_)));
        const Module = this.tryClass("<Module>");
        if (Module) {
          classes.unshift(Module);
        }
        return classes;
      } else {
        return globalThis.Array.from(globalThis.Array(this.classCount), (_, i) => new Il2Cpp3.Class(Il2Cpp3.exports.imageGetClass(this, i)));
      }
    }
    /** Gets the name of this image. */
    get name() {
      return Il2Cpp3.exports.imageGetName(this).readUtf8String();
    }
    /** Gets the class with the specified name defined in this image. */
    class(name) {
      return this.tryClass(name) ?? raise(`couldn't find class ${name} in assembly ${this.name}`);
    }
    /** Gets the class with the specified name defined in this image. */
    tryClass(name) {
      const dotIndex = name.lastIndexOf(".");
      const classNamespace = Memory.allocUtf8String(dotIndex == -1 ? "" : name.slice(0, dotIndex));
      const className = Memory.allocUtf8String(name.slice(dotIndex + 1));
      return new Il2Cpp3.Class(Il2Cpp3.exports.classFromName(this, classNamespace, className)).asNullable();
    }
  };
  __decorate([
    lazy
  ], Image.prototype, "assembly", null);
  __decorate([
    lazy
  ], Image.prototype, "classCount", null);
  __decorate([
    lazy
  ], Image.prototype, "classes", null);
  __decorate([
    lazy
  ], Image.prototype, "name", null);
  Image = __decorate([
    recycle
  ], Image);
  Il2Cpp3.Image = Image;
  getter(Il2Cpp3, "corlib", () => {
    return new Il2Cpp3.Image(Il2Cpp3.exports.getCorlib());
  }, lazy);
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class MemorySnapshot extends NativeStruct {
    /** Captures a memory snapshot. */
    static capture() {
      return new Il2Cpp3.MemorySnapshot();
    }
    /** Creates a memory snapshot with the given handle. */
    constructor(handle = Il2Cpp3.exports.memorySnapshotCapture()) {
      super(handle);
    }
    /** Gets any initialized class. */
    get classes() {
      return readNativeIterator((_) => Il2Cpp3.exports.memorySnapshotGetClasses(this, _)).map((_) => new Il2Cpp3.Class(_));
    }
    /** Gets the objects tracked by this memory snapshot. */
    get objects() {
      return readNativeList((_) => Il2Cpp3.exports.memorySnapshotGetObjects(this, _)).filter((_) => !_.isNull()).map((_) => new Il2Cpp3.Object(_));
    }
    /** Frees this memory snapshot. */
    free() {
      Il2Cpp3.exports.memorySnapshotFree(this);
    }
  }
  __decorate([
    lazy
  ], MemorySnapshot.prototype, "classes", null);
  __decorate([
    lazy
  ], MemorySnapshot.prototype, "objects", null);
  Il2Cpp3.MemorySnapshot = MemorySnapshot;
  function memorySnapshot(block) {
    const memorySnapshot2 = Il2Cpp3.MemorySnapshot.capture();
    const result = block(memorySnapshot2);
    memorySnapshot2.free();
    return result;
  }
  Il2Cpp3.memorySnapshot = memorySnapshot;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Method extends NativeStruct {
    /** Gets the class in which this method is defined. */
    get class() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.methodGetClass(this));
    }
    /** Gets the flags of the current method. */
    get flags() {
      return Il2Cpp3.exports.methodGetFlags(this, NULL);
    }
    /** Gets the implementation flags of the current method. */
    get implementationFlags() {
      const implementationFlagsPointer = Memory.alloc(Process.pointerSize);
      Il2Cpp3.exports.methodGetFlags(this, implementationFlagsPointer);
      return implementationFlagsPointer.readU32();
    }
    /** */
    get fridaSignature() {
      const types = [];
      for (const parameter of this.parameters) {
        types.push(parameter.type.fridaAlias);
      }
      if (!this.isStatic || Il2Cpp3.unityVersionIsBelow201830) {
        types.unshift("pointer");
      }
      if (this.isInflated) {
        types.push("pointer");
      }
      return types;
    }
    /** Gets the generic parameters of this generic method. */
    get generics() {
      if (!this.isGeneric) {
        return [];
      }
      const types = this.object.method("GetGenericArguments").invoke();
      return globalThis.Array.from(types).map((_) => new Il2Cpp3.Class(Il2Cpp3.exports.classFromObject(_)));
    }
    /** Determines whether this method is external. */
    get isExternal() {
      return (this.implementationFlags & 4096) != 0;
    }
    /** Determines whether this method is generic. */
    get isGeneric() {
      return !!Il2Cpp3.exports.methodIsGeneric(this);
    }
    /** Determines whether this method is inflated (generic with a concrete type parameter). */
    get isInflated() {
      return !!Il2Cpp3.exports.methodIsInflated(this);
    }
    /** Determines whether this method is static. */
    get isStatic() {
      return !Il2Cpp3.exports.methodIsInstance(this);
    }
    /** Determines whether this method is synchronized. */
    get isSynchronized() {
      return (this.implementationFlags & 32) != 0;
    }
    /** Gets the access modifier of this method. */
    get modifier() {
      switch (this.flags & 7) {
        case 1:
          return "private";
        case 2:
          return "private protected";
        case 3:
          return "internal";
        case 4:
          return "protected";
        case 5:
          return "protected internal";
        case 6:
          return "public";
      }
    }
    /** Gets the name of this method. */
    get name() {
      return Il2Cpp3.exports.methodGetName(this).readUtf8String();
    }
    /** @internal */
    get nativeFunction() {
      return new NativeFunction(this.virtualAddress, this.returnType.fridaAlias, this.fridaSignature);
    }
    /** Gets the encompassing object of the current method. */
    get object() {
      return new Il2Cpp3.Object(Il2Cpp3.exports.methodGetObject(this, NULL));
    }
    /** Gets the amount of parameters of this method. */
    get parameterCount() {
      return Il2Cpp3.exports.methodGetParameterCount(this);
    }
    /** Gets the parameters of this method. */
    get parameters() {
      return globalThis.Array.from(globalThis.Array(this.parameterCount), (_, i) => {
        const parameterName = Il2Cpp3.exports.methodGetParameterName(this, i).readUtf8String();
        const parameterType = Il2Cpp3.exports.methodGetParameterType(this, i);
        return new Il2Cpp3.Parameter(parameterName, i, new Il2Cpp3.Type(parameterType));
      });
    }
    /** Gets the relative virtual address (RVA) of this method. */
    get relativeVirtualAddress() {
      return this.virtualAddress.sub(Il2Cpp3.module.base);
    }
    /** Gets the return type of this method. */
    get returnType() {
      return new Il2Cpp3.Type(Il2Cpp3.exports.methodGetReturnType(this));
    }
    /** Gets the virtual address (VA) of this method. */
    get virtualAddress() {
      const FilterTypeName = Il2Cpp3.corlib.class("System.Reflection.Module").initialize().field("FilterTypeName").value;
      const FilterTypeNameMethodPointer = FilterTypeName.field("method_ptr").value;
      const FilterTypeNameMethod = FilterTypeName.field("method").value;
      const offset = FilterTypeNameMethod.offsetOf((_) => _.readPointer().equals(FilterTypeNameMethodPointer)) ?? raise("couldn't find the virtual address offset in the native method struct");
      getter(Il2Cpp3.Method.prototype, "virtualAddress", function() {
        return this.handle.add(offset).readPointer();
      }, lazy);
      Il2Cpp3.corlib.class("System.Reflection.Module").method(".cctor").invoke();
      return this.virtualAddress;
    }
    /** Replaces the body of this method. */
    set implementation(block) {
      try {
        Interceptor.replace(this.virtualAddress, this.wrap(block));
      } catch (e) {
        switch (e.message) {
          case "access violation accessing 0x0":
            raise(`couldn't set implementation for method ${this.name} as it has a NULL virtual address`);
          case /unable to intercept function at \w+; please file a bug/.exec(e.message)?.input:
            warn(`couldn't set implementation for method ${this.name} as it may be a thunk`);
            break;
          case "already replaced this function":
            warn(`couldn't set implementation for method ${this.name} as it has already been replaced by a thunk`);
            break;
          default:
            throw e;
        }
      }
    }
    /** Creates a generic instance of the current generic method. */
    inflate(...classes) {
      if (!this.isGeneric || this.generics.length != classes.length) {
        for (const method of this.overloads()) {
          if (method.isGeneric && method.generics.length == classes.length) {
            return method.inflate(...classes);
          }
        }
        raise(`could not find inflatable signature of method ${this.name} with ${classes.length} generic parameter(s)`);
      }
      const types = classes.map((_) => _.type.object);
      const typeArray = Il2Cpp3.array(Il2Cpp3.corlib.class("System.Type"), types);
      const inflatedMethodObject = this.object.method("MakeGenericMethod", 1).invoke(typeArray);
      return new Il2Cpp3.Method(inflatedMethodObject.field("mhandle").value);
    }
    /** Invokes this method. */
    invoke(...parameters) {
      if (!this.isStatic) {
        raise(`cannot invoke non-static method ${this.name} as it must be invoked throught a Il2Cpp.Object, not a Il2Cpp.Class`);
      }
      return this.invokeRaw(NULL, ...parameters);
    }
    /** @internal */
    invokeRaw(instance, ...parameters) {
      const allocatedParameters = parameters.map(Il2Cpp3.toFridaValue);
      if (!this.isStatic || Il2Cpp3.unityVersionIsBelow201830) {
        allocatedParameters.unshift(instance);
      }
      if (this.isInflated) {
        allocatedParameters.push(this.handle);
      }
      try {
        const returnValue = this.nativeFunction(...allocatedParameters);
        return Il2Cpp3.fromFridaValue(returnValue, this.returnType);
      } catch (e) {
        if (e == null) {
          raise("an unexpected native invocation exception occurred, this is due to parameter types mismatch");
        }
        switch (e.message) {
          case "bad argument count":
            raise(`couldn't invoke method ${this.name} as it needs ${this.parameterCount} parameter(s), not ${parameters.length}`);
          case "expected a pointer":
          case "expected number":
          case "expected array with fields":
            raise(`couldn't invoke method ${this.name} using incorrect parameter types`);
        }
        throw e;
      }
    }
    /** Gets the overloaded method with the given parameter types. */
    overload(...typeNamesOrClasses) {
      const method = this.tryOverload(...typeNamesOrClasses);
      return method ?? raise(`couldn't find overloaded method ${this.name}(${typeNamesOrClasses.map((_) => _ instanceof Il2Cpp3.Class ? _.type.name : _)})`);
    }
    /** @internal */
    *overloads() {
      for (const klass of this.class.hierarchy()) {
        for (const method of klass.methods) {
          if (this.name == method.name) {
            yield method;
          }
        }
      }
    }
    /** Gets the parameter with the given name. */
    parameter(name) {
      return this.tryParameter(name) ?? raise(`couldn't find parameter ${name} in method ${this.name}`);
    }
    /** Restore the original method implementation. */
    revert() {
      Interceptor.revert(this.virtualAddress);
      Interceptor.flush();
    }
    /** Gets the overloaded method with the given parameter types. */
    tryOverload(...typeNamesOrClasses) {
      const minScore = typeNamesOrClasses.length * 1;
      const maxScore = typeNamesOrClasses.length * 2;
      let candidate = void 0;
      loop: for (const method of this.overloads()) {
        if (method.parameterCount != typeNamesOrClasses.length)
          continue;
        let score = 0;
        let i = 0;
        for (const parameter of method.parameters) {
          const desiredTypeNameOrClass = typeNamesOrClasses[i];
          if (desiredTypeNameOrClass instanceof Il2Cpp3.Class) {
            if (parameter.type.is(desiredTypeNameOrClass.type)) {
              score += 2;
            } else if (parameter.type.class.isAssignableFrom(desiredTypeNameOrClass)) {
              score += 1;
            } else {
              continue loop;
            }
          } else if (parameter.type.name == desiredTypeNameOrClass) {
            score += 2;
          } else {
            continue loop;
          }
          i++;
        }
        if (score < minScore) {
          continue;
        } else if (score == maxScore) {
          return method;
        } else if (candidate == void 0 || score > candidate[0]) {
          candidate = [score, method];
        } else if (score == candidate[0]) {
          let i2 = 0;
          for (const parameter of candidate[1].parameters) {
            if (parameter.type.class.isAssignableFrom(method.parameters[i2].type.class)) {
              candidate = [score, method];
              continue loop;
            }
            i2++;
          }
        }
      }
      return candidate?.[1];
    }
    /** Gets the parameter with the given name. */
    tryParameter(name) {
      return this.parameters.find((_) => _.name == name);
    }
    /** */
    toString() {
      return `${this.isStatic ? `static ` : ``}${this.returnType.name} ${this.name}${this.generics.length > 0 ? `<${this.generics.map((_) => _.type.name).join(",")}>` : ""}(${this.parameters.join(`, `)});${this.virtualAddress.isNull() ? `` : ` // 0x${this.relativeVirtualAddress.toString(16).padStart(8, `0`)}`}`;
    }
    /**
     * @internal
     * Binds the current method to a {@link Il2Cpp.Object} or a
     * {@link Il2Cpp.ValueType} (also known as *instances*), so that it is
     * possible to invoke it - see {@link Il2Cpp.Method.invoke} for
     * details. \
     * Binding a static method is forbidden.
     */
    bind(instance) {
      if (this.isStatic) {
        raise(`cannot bind static method ${this.class.type.name}::${this.name} to an instance`);
      }
      return new Proxy(this, {
        get(target, property, receiver) {
          switch (property) {
            case "invoke":
              const handle = instance instanceof Il2Cpp3.ValueType ? target.class.isValueType ? instance.handle.sub(structMethodsRequireObjectInstances() ? Il2Cpp3.Object.headerSize : 0) : raise(`cannot invoke method ${target.class.type.name}::${target.name} against a value type, you must box it first`) : target.class.isValueType ? instance.handle.add(structMethodsRequireObjectInstances() ? 0 : Il2Cpp3.Object.headerSize) : instance.handle;
              return target.invokeRaw.bind(target, handle);
            case "overloads":
              return function* () {
                for (const method of target[property]()) {
                  if (!method.isStatic) {
                    yield method;
                  }
                }
              };
            case "inflate":
            case "overload":
            case "tryOverload":
              const member = Reflect.get(target, property).bind(receiver);
              return function(...args) {
                return member(...args)?.bind(instance);
              };
          }
          return Reflect.get(target, property);
        }
      });
    }
    /** @internal */
    wrap(block) {
      const startIndex = +!this.isStatic | +Il2Cpp3.unityVersionIsBelow201830;
      return new NativeCallback((...args) => {
        const thisObject = this.isStatic ? this.class : this.class.isValueType ? new Il2Cpp3.ValueType(args[0].add(structMethodsRequireObjectInstances() ? Il2Cpp3.Object.headerSize : 0), this.class.type) : new Il2Cpp3.Object(args[0]);
        const parameters = this.parameters.map((_, i) => Il2Cpp3.fromFridaValue(args[i + startIndex], _.type));
        const result = block.call(thisObject, ...parameters);
        return Il2Cpp3.toFridaValue(result);
      }, this.returnType.fridaAlias, this.fridaSignature);
    }
  }
  __decorate([
    lazy
  ], Method.prototype, "class", null);
  __decorate([
    lazy
  ], Method.prototype, "flags", null);
  __decorate([
    lazy
  ], Method.prototype, "implementationFlags", null);
  __decorate([
    lazy
  ], Method.prototype, "fridaSignature", null);
  __decorate([
    lazy
  ], Method.prototype, "generics", null);
  __decorate([
    lazy
  ], Method.prototype, "isExternal", null);
  __decorate([
    lazy
  ], Method.prototype, "isGeneric", null);
  __decorate([
    lazy
  ], Method.prototype, "isInflated", null);
  __decorate([
    lazy
  ], Method.prototype, "isStatic", null);
  __decorate([
    lazy
  ], Method.prototype, "isSynchronized", null);
  __decorate([
    lazy
  ], Method.prototype, "modifier", null);
  __decorate([
    lazy
  ], Method.prototype, "name", null);
  __decorate([
    lazy
  ], Method.prototype, "nativeFunction", null);
  __decorate([
    lazy
  ], Method.prototype, "object", null);
  __decorate([
    lazy
  ], Method.prototype, "parameterCount", null);
  __decorate([
    lazy
  ], Method.prototype, "parameters", null);
  __decorate([
    lazy
  ], Method.prototype, "relativeVirtualAddress", null);
  __decorate([
    lazy
  ], Method.prototype, "returnType", null);
  Il2Cpp3.Method = Method;
  let structMethodsRequireObjectInstances = () => {
    const object = Il2Cpp3.corlib.class("System.Int64").alloc();
    object.field("m_value").value = 3735928559;
    const result = object.method("Equals", 1).overload(object.class).invokeRaw(object, 3735928559);
    return (structMethodsRequireObjectInstances = () => result)();
  };
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Object2 extends NativeStruct {
    /** Gets the Il2CppObject struct size, possibly equal to `Process.pointerSize * 2`. */
    static get headerSize() {
      return Il2Cpp3.corlib.class("System.Object").instanceSize;
    }
    /**
     * Returns the same object, but having its parent class as class.
     * It basically is the C# `base` keyword, so that parent members can be
     * accessed.
     *
     * **Example** \
     * Consider the following classes:
     * ```csharp
     * class Foo
     * {
     *     int foo()
     *     {
     *          return 1;
     *     }
     * }
     * class Bar : Foo
     * {
     *     new int foo()
     *     {
     *          return 2;
     *     }
     * }
     * ```
     * then:
     * ```ts
     * const Bar: Il2Cpp.Class = ...;
     * const bar = Bar.new();
     *
     * console.log(bar.foo()); // 2
     * console.log(bar.base.foo()); // 1
     * ```
     */
    get base() {
      if (this.class.parent == null) {
        raise(`class ${this.class.type.name} has no parent`);
      }
      return new Proxy(this, {
        get(target, property, receiver) {
          if (property == "class") {
            return Reflect.get(target, property).parent;
          } else if (property == "base") {
            return Reflect.getOwnPropertyDescriptor(Il2Cpp3.Object.prototype, property).get.bind(receiver)();
          }
          return Reflect.get(target, property);
        }
      });
    }
    /** Gets the class of this object. */
    get class() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.objectGetClass(this));
    }
    /** Returns a monitor for this object. */
    get monitor() {
      return new Il2Cpp3.Object.Monitor(this);
    }
    /** Gets the size of the current object. */
    get size() {
      return Il2Cpp3.exports.objectGetSize(this);
    }
    /** Gets the non-static field with the given name of the current class hierarchy. */
    field(name) {
      return this.tryField(name) ?? raise(`couldn't find non-static field ${name} in hierarchy of class ${this.class.type.name}`);
    }
    /** Gets the non-static method with the given name (and optionally parameter count) of the current class hierarchy. */
    method(name, parameterCount = -1) {
      return this.tryMethod(name, parameterCount) ?? raise(`couldn't find non-static method ${name} in hierarchy of class ${this.class.type.name}`);
    }
    /** Creates a reference to this object. */
    ref(pin) {
      return new Il2Cpp3.GCHandle(Il2Cpp3.exports.gcHandleNew(this, +pin));
    }
    /** Gets the correct virtual method from the given virtual method. */
    virtualMethod(method) {
      return new Il2Cpp3.Method(Il2Cpp3.exports.objectGetVirtualMethod(this, method)).bind(this);
    }
    /** Gets the non-static field with the given name of the current class hierarchy, if it exists. */
    tryField(name) {
      const field = this.class.tryField(name);
      if (field?.isStatic) {
        for (const klass of this.class.hierarchy({ includeCurrent: false })) {
          for (const field2 of klass.fields) {
            if (field2.name == name && !field2.isStatic) {
              return field2.bind(this);
            }
          }
        }
        return void 0;
      }
      return field?.bind(this);
    }
    /** Gets the non-static method with the given name (and optionally parameter count) of the current class hierarchy, if it exists. */
    tryMethod(name, parameterCount = -1) {
      const method = this.class.tryMethod(name, parameterCount);
      if (method?.isStatic) {
        for (const klass of this.class.hierarchy()) {
          for (const method2 of klass.methods) {
            if (method2.name == name && !method2.isStatic && (parameterCount < 0 || method2.parameterCount == parameterCount)) {
              return method2.bind(this);
            }
          }
        }
        return void 0;
      }
      return method?.bind(this);
    }
    /** */
    toString() {
      return this.isNull() ? "null" : this.method("ToString", 0).invoke().content ?? "null";
    }
    /** Unboxes the value type (either a primitive, a struct or an enum) out of this object. */
    unbox() {
      return this.class.isValueType ? new Il2Cpp3.ValueType(Il2Cpp3.exports.objectUnbox(this), this.class.type) : raise(`couldn't unbox instances of ${this.class.type.name} as they are not value types`);
    }
    /** Creates a weak reference to this object. */
    weakRef(trackResurrection) {
      return new Il2Cpp3.GCHandle(Il2Cpp3.exports.gcHandleNewWeakRef(this, +trackResurrection));
    }
  }
  __decorate([
    lazy
  ], Object2.prototype, "class", null);
  __decorate([
    lazy
  ], Object2.prototype, "size", null);
  __decorate([
    lazy
  ], Object2, "headerSize", null);
  Il2Cpp3.Object = Object2;
  (function(Object3) {
    class Monitor {
      handle;
      /** @internal */
      constructor(handle) {
        this.handle = handle;
      }
      /** Acquires an exclusive lock on the current object. */
      enter() {
        return Il2Cpp3.exports.monitorEnter(this.handle);
      }
      /** Release an exclusive lock on the current object. */
      exit() {
        return Il2Cpp3.exports.monitorExit(this.handle);
      }
      /** Notifies a thread in the waiting queue of a change in the locked object's state. */
      pulse() {
        return Il2Cpp3.exports.monitorPulse(this.handle);
      }
      /** Notifies all waiting threads of a change in the object's state. */
      pulseAll() {
        return Il2Cpp3.exports.monitorPulseAll(this.handle);
      }
      /** Attempts to acquire an exclusive lock on the current object. */
      tryEnter(timeout) {
        return !!Il2Cpp3.exports.monitorTryEnter(this.handle, timeout);
      }
      /** Releases the lock on an object and attempts to block the current thread until it reacquires the lock. */
      tryWait(timeout) {
        return !!Il2Cpp3.exports.monitorTryWait(this.handle, timeout);
      }
      /** Releases the lock on an object and blocks the current thread until it reacquires the lock. */
      wait() {
        return Il2Cpp3.exports.monitorWait(this.handle);
      }
    }
    Object3.Monitor = Monitor;
  })(Object2 = Il2Cpp3.Object || (Il2Cpp3.Object = {}));
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Parameter {
    /** Name of this parameter. */
    name;
    /** Position of this parameter. */
    position;
    /** Type of this parameter. */
    type;
    constructor(name, position, type) {
      this.name = name;
      this.position = position;
      this.type = type;
    }
    /** */
    toString() {
      return `${this.type.name} ${this.name}`;
    }
  }
  Il2Cpp3.Parameter = Parameter;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Pointer extends NativeStruct {
    type;
    constructor(handle, type) {
      super(handle);
      this.type = type;
    }
    /** Gets the element at the given index. */
    get(index) {
      return Il2Cpp3.read(this.handle.add(index * this.type.class.arrayElementSize), this.type);
    }
    /** Reads the given amount of elements starting at the given offset. */
    read(length, offset = 0) {
      const values = new globalThis.Array(length);
      for (let i = 0; i < length; i++) {
        values[i] = this.get(i + offset);
      }
      return values;
    }
    /** Sets the given element at the given index */
    set(index, value) {
      Il2Cpp3.write(this.handle.add(index * this.type.class.arrayElementSize), value, this.type);
    }
    /** */
    toString() {
      return this.handle.toString();
    }
    /** Writes the given elements starting at the given index. */
    write(values, offset = 0) {
      for (let i = 0; i < values.length; i++) {
        this.set(i + offset, values[i]);
      }
    }
  }
  Il2Cpp3.Pointer = Pointer;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Reference extends NativeStruct {
    type;
    constructor(handle, type) {
      super(handle);
      this.type = type;
    }
    /** Gets the element referenced by the current reference. */
    get value() {
      return Il2Cpp3.read(this.handle, this.type);
    }
    /** Sets the element referenced by the current reference. */
    set value(value) {
      Il2Cpp3.write(this.handle, value, this.type);
    }
    /** */
    toString() {
      return this.isNull() ? "null" : `->${this.value}`;
    }
  }
  Il2Cpp3.Reference = Reference;
  function reference(value, type) {
    const handle = Memory.alloc(Process.pointerSize);
    switch (typeof value) {
      case "boolean":
        return new Il2Cpp3.Reference(handle.writeS8(+value), Il2Cpp3.corlib.class("System.Boolean").type);
      case "number":
        switch (type?.enumValue) {
          case Il2Cpp3.Type.Enum.UBYTE:
            return new Il2Cpp3.Reference(handle.writeU8(value), type);
          case Il2Cpp3.Type.Enum.BYTE:
            return new Il2Cpp3.Reference(handle.writeS8(value), type);
          case Il2Cpp3.Type.Enum.CHAR:
          case Il2Cpp3.Type.Enum.USHORT:
            return new Il2Cpp3.Reference(handle.writeU16(value), type);
          case Il2Cpp3.Type.Enum.SHORT:
            return new Il2Cpp3.Reference(handle.writeS16(value), type);
          case Il2Cpp3.Type.Enum.UINT:
            return new Il2Cpp3.Reference(handle.writeU32(value), type);
          case Il2Cpp3.Type.Enum.INT:
            return new Il2Cpp3.Reference(handle.writeS32(value), type);
          case Il2Cpp3.Type.Enum.ULONG:
            return new Il2Cpp3.Reference(handle.writeU64(value), type);
          case Il2Cpp3.Type.Enum.LONG:
            return new Il2Cpp3.Reference(handle.writeS64(value), type);
          case Il2Cpp3.Type.Enum.FLOAT:
            return new Il2Cpp3.Reference(handle.writeFloat(value), type);
          case Il2Cpp3.Type.Enum.DOUBLE:
            return new Il2Cpp3.Reference(handle.writeDouble(value), type);
        }
      case "object":
        if (value instanceof Il2Cpp3.ValueType || value instanceof Il2Cpp3.Pointer) {
          return new Il2Cpp3.Reference(value.handle, value.type);
        } else if (value instanceof Il2Cpp3.Object) {
          return new Il2Cpp3.Reference(handle.writePointer(value), value.class.type);
        } else if (value instanceof Il2Cpp3.String || value instanceof Il2Cpp3.Array) {
          return new Il2Cpp3.Reference(handle.writePointer(value), value.object.class.type);
        } else if (value instanceof NativePointer) {
          switch (type?.enumValue) {
            case Il2Cpp3.Type.Enum.NUINT:
            case Il2Cpp3.Type.Enum.NINT:
              return new Il2Cpp3.Reference(handle.writePointer(value), type);
          }
        } else if (value instanceof Int64) {
          return new Il2Cpp3.Reference(handle.writeS64(value), Il2Cpp3.corlib.class("System.Int64").type);
        } else if (value instanceof UInt64) {
          return new Il2Cpp3.Reference(handle.writeU64(value), Il2Cpp3.corlib.class("System.UInt64").type);
        }
      default:
        raise(`couldn't create a reference to ${value} using an unhandled type ${type?.name}`);
    }
  }
  Il2Cpp3.reference = reference;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class String2 extends NativeStruct {
    /** Gets the content of this string. */
    get content() {
      return Il2Cpp3.exports.stringGetChars(this).readUtf16String(this.length);
    }
    /** @unsafe Sets the content of this string - it may write out of bounds! */
    set content(value) {
      const offset = Il2Cpp3.string("vfsfitvnm").handle.offsetOf((_) => _.readInt() == 9) ?? raise("couldn't find the length offset in the native string struct");
      globalThis.Object.defineProperty(Il2Cpp3.String.prototype, "content", {
        set(value2) {
          Il2Cpp3.exports.stringGetChars(this).writeUtf16String(value2 ?? "");
          this.handle.add(offset).writeS32(value2?.length ?? 0);
        }
      });
      this.content = value;
    }
    /** Gets the length of this string. */
    get length() {
      return Il2Cpp3.exports.stringGetLength(this);
    }
    /** Gets the encompassing object of the current string. */
    get object() {
      return new Il2Cpp3.Object(this);
    }
    /** */
    toString() {
      return this.isNull() ? "null" : `"${this.content}"`;
    }
  }
  Il2Cpp3.String = String2;
  function string(content) {
    return new Il2Cpp3.String(Il2Cpp3.exports.stringNew(Memory.allocUtf8String(content ?? "")));
  }
  Il2Cpp3.string = string;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class Thread extends NativeStruct {
    /** Gets the native id of the current thread. */
    get id() {
      let get = function() {
        return this.internal.field("thread_id").value.toNumber();
      };
      if (Process.platform != "windows") {
        const currentThreadId = Process.getCurrentThreadId();
        const currentPosixThread = ptr(get.apply(Il2Cpp3.currentThread));
        const offset = currentPosixThread.offsetOf((_) => _.readS32() == currentThreadId, 1024) ?? raise(`couldn't find the offset for determining the kernel id of a posix thread`);
        const _get = get;
        get = function() {
          return ptr(_get.apply(this)).add(offset).readS32();
        };
      }
      getter(Il2Cpp3.Thread.prototype, "id", get, lazy);
      return this.id;
    }
    /** Gets the encompassing internal object (System.Threding.InternalThreead) of the current thread. */
    get internal() {
      return this.object.tryField("internal_thread")?.value ?? this.object;
    }
    /** Determines whether the current thread is the garbage collector finalizer one. */
    get isFinalizer() {
      return !Il2Cpp3.exports.threadIsVm(this);
    }
    /** Gets the managed id of the current thread. */
    get managedId() {
      return this.object.method("get_ManagedThreadId").invoke();
    }
    /** Gets the encompassing object of the current thread. */
    get object() {
      return new Il2Cpp3.Object(this);
    }
    /** @internal */
    get staticData() {
      return this.internal.field("static_data").value;
    }
    /** @internal */
    get synchronizationContext() {
      const get_ExecutionContext = this.object.tryMethod("GetMutableExecutionContext") ?? this.object.method("get_ExecutionContext");
      const executionContext = get_ExecutionContext.invoke();
      const synchronizationContext = executionContext.tryField("_syncContext")?.value ?? executionContext.tryMethod("get_SynchronizationContext")?.invoke() ?? this.tryLocalValue(Il2Cpp3.corlib.class("System.Threading.SynchronizationContext"));
      return synchronizationContext?.asNullable() ?? null;
    }
    /** Detaches the thread from the application domain. */
    detach() {
      return Il2Cpp3.exports.threadDetach(this);
    }
    /** Schedules a callback on the current thread. */
    schedule(block) {
      const Post = this.synchronizationContext?.tryMethod("Post");
      if (Post == null) {
        return Process.runOnThread(this.id, block);
      }
      return new Promise((resolve) => {
        const delegate = Il2Cpp3.delegate(Il2Cpp3.corlib.class("System.Threading.SendOrPostCallback"), () => {
          const result = block();
          setImmediate(() => resolve(result));
        });
        Script.bindWeak(globalThis, () => {
          delegate.field("method_ptr").value = delegate.field("invoke_impl").value = Il2Cpp3.exports.domainGet;
        });
        Post.invoke(delegate, NULL);
      });
    }
    /** @internal */
    tryLocalValue(klass) {
      for (let i = 0; i < 16; i++) {
        const base = this.staticData.add(i * Process.pointerSize).readPointer();
        if (!base.isNull()) {
          const object = new Il2Cpp3.Object(base.readPointer()).asNullable();
          if (object?.class?.isSubclassOf(klass, false)) {
            return object;
          }
        }
      }
    }
  }
  __decorate([
    lazy
  ], Thread.prototype, "internal", null);
  __decorate([
    lazy
  ], Thread.prototype, "isFinalizer", null);
  __decorate([
    lazy
  ], Thread.prototype, "managedId", null);
  __decorate([
    lazy
  ], Thread.prototype, "object", null);
  __decorate([
    lazy
  ], Thread.prototype, "staticData", null);
  __decorate([
    lazy
  ], Thread.prototype, "synchronizationContext", null);
  Il2Cpp3.Thread = Thread;
  getter(Il2Cpp3, "attachedThreads", () => {
    if (Il2Cpp3.exports.threadGetAttachedThreads.isNull()) {
      const currentThreadHandle = Il2Cpp3.currentThread?.handle ?? raise("Current thread is not attached to IL2CPP");
      const pattern = currentThreadHandle.toMatchPattern();
      const threads = [];
      for (const range of Process.enumerateRanges("rw-")) {
        if (range.file == void 0) {
          const matches = Memory.scanSync(range.base, range.size, pattern);
          if (matches.length == 1) {
            while (true) {
              const handle = matches[0].address.sub(matches[0].size * threads.length).readPointer();
              if (handle.isNull() || !handle.readPointer().equals(currentThreadHandle.readPointer())) {
                break;
              }
              threads.unshift(new Il2Cpp3.Thread(handle));
            }
            break;
          }
        }
      }
      return threads;
    }
    return readNativeList(Il2Cpp3.exports.threadGetAttachedThreads).map((_) => new Il2Cpp3.Thread(_));
  });
  getter(Il2Cpp3, "currentThread", () => {
    return new Il2Cpp3.Thread(Il2Cpp3.exports.threadGetCurrent()).asNullable();
  });
  getter(Il2Cpp3, "mainThread", () => {
    return Il2Cpp3.attachedThreads[0];
  });
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  let Type = class Type extends NativeStruct {
    /** */
    static get Enum() {
      const _ = (_2, block = (_3) => _3) => block(Il2Cpp3.corlib.class(_2)).type.enumValue;
      const initial = {
        VOID: _("System.Void"),
        BOOLEAN: _("System.Boolean"),
        CHAR: _("System.Char"),
        BYTE: _("System.SByte"),
        UBYTE: _("System.Byte"),
        SHORT: _("System.Int16"),
        USHORT: _("System.UInt16"),
        INT: _("System.Int32"),
        UINT: _("System.UInt32"),
        LONG: _("System.Int64"),
        ULONG: _("System.UInt64"),
        NINT: _("System.IntPtr"),
        NUINT: _("System.UIntPtr"),
        FLOAT: _("System.Single"),
        DOUBLE: _("System.Double"),
        POINTER: _("System.IntPtr", (_2) => _2.field("m_value")),
        VALUE_TYPE: _("System.Decimal"),
        OBJECT: _("System.Object"),
        STRING: _("System.String"),
        CLASS: _("System.Array"),
        ARRAY: _("System.Void", (_2) => _2.arrayClass),
        NARRAY: _("System.Void", (_2) => new Il2Cpp3.Class(Il2Cpp3.exports.classGetArrayClass(_2, 2))),
        GENERIC_INSTANCE: _("System.Int32", (_2) => _2.interfaces.find((_3) => _3.name.endsWith("`1")))
      };
      Reflect.defineProperty(this, "Enum", { value: initial });
      return addFlippedEntries({
        ...initial,
        VAR: _("System.Action`1", (_2) => _2.generics[0]),
        MVAR: _("System.Array", (_2) => _2.method("AsReadOnly", 1).generics[0])
      });
    }
    /** Gets the class of this type. */
    get class() {
      return new Il2Cpp3.Class(Il2Cpp3.exports.typeGetClass(this));
    }
    /** */
    get fridaAlias() {
      function getValueTypeFields(type) {
        const instanceFields = type.class.fields.filter((_) => !_.isStatic);
        return instanceFields.length == 0 ? ["char"] : instanceFields.map((_) => _.type.fridaAlias);
      }
      if (this.isByReference) {
        return "pointer";
      }
      switch (this.enumValue) {
        case Il2Cpp3.Type.Enum.VOID:
          return "void";
        case Il2Cpp3.Type.Enum.BOOLEAN:
          return "bool";
        case Il2Cpp3.Type.Enum.CHAR:
          return "uchar";
        case Il2Cpp3.Type.Enum.BYTE:
          return "int8";
        case Il2Cpp3.Type.Enum.UBYTE:
          return "uint8";
        case Il2Cpp3.Type.Enum.SHORT:
          return "int16";
        case Il2Cpp3.Type.Enum.USHORT:
          return "uint16";
        case Il2Cpp3.Type.Enum.INT:
          return "int32";
        case Il2Cpp3.Type.Enum.UINT:
          return "uint32";
        case Il2Cpp3.Type.Enum.LONG:
          return "int64";
        case Il2Cpp3.Type.Enum.ULONG:
          return "uint64";
        case Il2Cpp3.Type.Enum.FLOAT:
          return "float";
        case Il2Cpp3.Type.Enum.DOUBLE:
          return "double";
        case Il2Cpp3.Type.Enum.NINT:
        case Il2Cpp3.Type.Enum.NUINT:
        case Il2Cpp3.Type.Enum.POINTER:
        case Il2Cpp3.Type.Enum.STRING:
        case Il2Cpp3.Type.Enum.ARRAY:
        case Il2Cpp3.Type.Enum.NARRAY:
          return "pointer";
        case Il2Cpp3.Type.Enum.VALUE_TYPE:
          return this.class.isEnum ? this.class.baseType.fridaAlias : getValueTypeFields(this);
        case Il2Cpp3.Type.Enum.CLASS:
        case Il2Cpp3.Type.Enum.OBJECT:
        case Il2Cpp3.Type.Enum.GENERIC_INSTANCE:
          return this.class.isStruct ? getValueTypeFields(this) : this.class.isEnum ? this.class.baseType.fridaAlias : "pointer";
        default:
          return "pointer";
      }
    }
    /** Determines whether this type is passed by reference. */
    get isByReference() {
      return this.name.endsWith("&");
    }
    /** Determines whether this type is primitive. */
    get isPrimitive() {
      switch (this.enumValue) {
        case Il2Cpp3.Type.Enum.BOOLEAN:
        case Il2Cpp3.Type.Enum.CHAR:
        case Il2Cpp3.Type.Enum.BYTE:
        case Il2Cpp3.Type.Enum.UBYTE:
        case Il2Cpp3.Type.Enum.SHORT:
        case Il2Cpp3.Type.Enum.USHORT:
        case Il2Cpp3.Type.Enum.INT:
        case Il2Cpp3.Type.Enum.UINT:
        case Il2Cpp3.Type.Enum.LONG:
        case Il2Cpp3.Type.Enum.ULONG:
        case Il2Cpp3.Type.Enum.FLOAT:
        case Il2Cpp3.Type.Enum.DOUBLE:
        case Il2Cpp3.Type.Enum.NINT:
        case Il2Cpp3.Type.Enum.NUINT:
          return true;
        default:
          return false;
      }
    }
    /** Gets the name of this type. */
    get name() {
      const handle = Il2Cpp3.exports.typeGetName(this);
      try {
        return handle.readUtf8String();
      } finally {
        Il2Cpp3.free(handle);
      }
    }
    /** Gets the encompassing object of the current type. */
    get object() {
      return new Il2Cpp3.Object(Il2Cpp3.exports.typeGetObject(this));
    }
    /** Gets the {@link Il2Cpp.Type.Enum} value of the current type. */
    get enumValue() {
      return Il2Cpp3.exports.typeGetTypeEnum(this);
    }
    is(other) {
      if (Il2Cpp3.exports.typeEquals.isNull()) {
        return this.object.method("Equals").invoke(other.object);
      }
      return !!Il2Cpp3.exports.typeEquals(this, other);
    }
    /** */
    toString() {
      return this.name;
    }
  };
  __decorate([
    lazy
  ], Type.prototype, "class", null);
  __decorate([
    lazy
  ], Type.prototype, "fridaAlias", null);
  __decorate([
    lazy
  ], Type.prototype, "isByReference", null);
  __decorate([
    lazy
  ], Type.prototype, "isPrimitive", null);
  __decorate([
    lazy
  ], Type.prototype, "name", null);
  __decorate([
    lazy
  ], Type.prototype, "object", null);
  __decorate([
    lazy
  ], Type.prototype, "enumValue", null);
  __decorate([
    lazy
  ], Type, "Enum", null);
  Type = __decorate([
    recycle
  ], Type);
  Il2Cpp3.Type = Type;
})(Il2Cpp2 || (Il2Cpp2 = {}));
var Il2Cpp2;
(function(Il2Cpp3) {
  class ValueType extends NativeStruct {
    type;
    constructor(handle, type) {
      super(handle);
      this.type = type;
    }
    /** Boxes the current value type in a object. */
    box() {
      return new Il2Cpp3.Object(Il2Cpp3.exports.valueTypeBox(this.type.class, this));
    }
    /** Gets the non-static field with the given name of the current class hierarchy. */
    field(name) {
      return this.tryField(name) ?? raise(`couldn't find non-static field ${name} in hierarchy of class ${this.type.name}`);
    }
    /** Gets the non-static method with the given name (and optionally parameter count) of the current class hierarchy. */
    method(name, parameterCount = -1) {
      return this.tryMethod(name, parameterCount) ?? raise(`couldn't find non-static method ${name} in hierarchy of class ${this.type.name}`);
    }
    /** Gets the non-static field with the given name of the current class hierarchy, if it exists. */
    tryField(name) {
      const field = this.type.class.tryField(name);
      if (field?.isStatic) {
        for (const klass of this.type.class.hierarchy()) {
          for (const field2 of klass.fields) {
            if (field2.name == name && !field2.isStatic) {
              return field2.bind(this);
            }
          }
        }
        return void 0;
      }
      return field?.bind(this);
    }
    /** Gets the non-static method with the given name (and optionally parameter count) of the current class hierarchy, if it exists. */
    tryMethod(name, parameterCount = -1) {
      const method = this.type.class.tryMethod(name, parameterCount);
      if (method?.isStatic) {
        for (const klass of this.type.class.hierarchy()) {
          for (const method2 of klass.methods) {
            if (method2.name == name && !method2.isStatic && (parameterCount < 0 || method2.parameterCount == parameterCount)) {
              return method2.bind(this);
            }
          }
        }
        return void 0;
      }
      return method?.bind(this);
    }
    /** */
    toString() {
      const ToString = this.method("ToString", 0);
      return this.isNull() ? "null" : (
        // If ToString is defined within a value type class, we can
        // avoid a boxing operation.
        ToString.class.isValueType ? ToString.invoke().content ?? "null" : this.box().toString() ?? "null"
      );
    }
  }
  Il2Cpp3.ValueType = ValueType;
})(Il2Cpp2 || (Il2Cpp2 = {}));
globalThis.Il2Cpp = Il2Cpp2;

// matchmasters_board_dump.ts
var EXPECTED_OFFSETS = {
  "GameLogic.board": 184,
  "GameLogic.currentGameState": 208,
  "GameLogic.isAISimulation": 232,
  "BoardModel.slots": 32,
  "SlotModel.color": 16,
  "SlotModel.color2": 17,
  "SlotModel.value": 18,
  "SlotModel.originalValue": 19,
  "SlotModel.holdValue": 20,
  "SlotModel.relatedPlayerIndex": 21,
  "SlotModel.status": 24,
  "SlotModel.score": 28,
  "SlotModel.scoreModifierOrigin": 29,
  "SlotModel.scoreModifierBonus": 30,
  "SlotModel.energy": 31,
  "SlotModel.hitPoints": 32,
  "SlotModel.origin": 44
};
var SLOT_FALLBACKS = {
  color: [16, "u8"],
  color2: [17, "u8"],
  value: [18, "u8"],
  originalValue: [19, "u8"],
  holdValue: [20, "u8"],
  relatedPlayerIndex: [21, "u8"],
  status: [24, "u32"],
  score: [28, "u8"],
  scoreModifierOrigin: [29, "u8"],
  scoreModifierBonus: [30, "u8"],
  energy: [31, "u8"],
  hitPoints: [32, "u8"],
  damageable: [33, "bool"],
  autoDestruct: [35, "bool"],
  canBeMatched: [36, "bool"],
  movable: [37, "bool"],
  createdFromCombo: [38, "bool"],
  skipDestroyTillMoveEnds: [39, "bool"],
  activateOnHitpointReduced: [40, "bool"],
  origin: [44, "u32"],
  isLiveEventPiece: [48, "bool"]
};
var gameLogicClass = null;
var gameDataClass = null;
var boardClass = null;
var slotClass = null;
var cachedGameLogic = null;
var froggyClass = null;
var cachedFroggy = null;
var ABILITY_CHOOSE_BLIND_PER_MATCH = 1;
var ABILITY_CHOOSE_HINTED_PER_MATCH = 3;
var ABILITY_CHOOSE_SPACING_MS = 1e4;
var ABILITY_TYPE_JELLY_SE = 60;
var ABILITY_TYPE_FROGGY_FU = 63;
var froggyChooses = 0;
var froggyChooseAfter = 0;
var IN_MATCH_RESOLVE_WALKS_PER_MATCH = 2;
var IN_MATCH_RESOLVE_SPACING_MS = 5e3;
var inMatchResolveWalks = 0;
var inMatchResolveAfter = 0;
var FROGGY_LOTUS_SLOT_VALUE = 40;
var jellyClass = null;
var cachedJelly = null;
var jellyChooses = 0;
var jellyChooseAfter = 0;
var chooseCount = 0;
var lastChooseWhy = null;
var lastChooseMs = null;
var lastChooseAt = null;
var HEARTBEAT_ACTIVE_MS = 1e3;
var HEARTBEAT_IDLE_MS = 5e3;
var heartbeatAfter = 0;
var lastTickMs = 0;
var maxTickMs = 0;
var JELLY_EXTRA_DATA_HINT = /jelly|infected/i;
var cachedJellyKeys = null;
var jellyDeepAfter = 0;
var JELLY_DEEP_INTERVAL_MS = 500;
var cachedExtraDataBoard = null;
var extraDataScanned = false;
var pollTimer = null;
var pollMilliseconds = 250;
var idleMilliseconds = 1e3;
var matchActive = false;
var lastGameCount = null;
var lastChangeTimestamp = 0;
var idleAfterQuietMs = 0;
var consecutivePollErrors = 0;
var recheckAfter = 0;
var IDLE_RECHECK_MS = 5e3;
var idleChooseAfter = 0;
var IDLE_CHOOSE_COST_FACTOR = 20;
var IDLE_CHOOSE_MAX_DELAY_MS = 8e3;
var IDLE_WALK_INTERVAL_MS = 6e4;
var deferredResolves = 0;
var budgetMatchHandle = null;
var stateCheckAfter = 0;
var IDLE_STATE_CHECK_MS = 2e3;
var attachProbe = null;
var pendingMatchUntil = 0;
var pendingSince = null;
var PENDING_MATCH_MS = 3e4;
var useCtorHook = true;
var ctorHookState = "off";
var ctorHookError = null;
var constructedHandle = null;
var ctorHookListeners = [];
var ctorHookDetachPending = false;
var constructedSeen = null;
var constructedCount = 0;
var CONSTRUCTED_RING_MAX = 32;
var constructedRing = [];
var ringScannedAtCount = -1;
var resolveByHook = 0;
var resolveByChoose = 0;
var concedeHookState = "off";
var concedeHookError = null;
var concededAt = null;
var disposeHookState = "off";
var disposeHookError = null;
var disposedHandle = null;
var disposedAt = null;
var disposedCount = 0;
var endedLogicHandle = null;
function isEndedLogic(instance) {
  if (endedLogicHandle == null) return false;
  try {
    return instance.handle.toString() === endedLogicHandle;
  } catch (_) {
    return false;
  }
}
var deadLogicKeys = /* @__PURE__ */ new Set();
var DEAD_LOGIC_KEYS_MAX = 64;
var SOFT_END_REASONS = /* @__PURE__ */ new Set(["tabla se ne menja", "nema table", "GameLogic je nestao"]);
function boardPointerOf(instance) {
  try {
    const board = instance.field("board").value;
    return board == null ? "0" : board.handle.toString();
  } catch (_) {
    try {
      return instance.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer().toString();
    } catch (_2) {
      return "?";
    }
  }
}
function logicKey(instance) {
  try {
    return `${instance.handle.toString()}/${boardPointerOf(instance)}`;
  } catch (_) {
    return null;
  }
}
function isDeadLogic(instance) {
  if (deadLogicKeys.size === 0) return false;
  const key = logicKey(instance);
  return key != null && deadLogicKeys.has(key);
}
function markLogicDead(key) {
  if (key == null) return;
  deadLogicKeys.add(key);
  while (deadLogicKeys.size > DEAD_LOGIC_KEYS_MAX) {
    const oldest = deadLogicKeys.values().next().value;
    if (oldest == null) break;
    deadLogicKeys.delete(oldest);
  }
}
function readGameIndex(instance) {
  try {
    const field = instance.tryField("<GameIndex>k__BackingField");
    if (field != null) return asNumber(field.value);
  } catch (_) {
  }
  return null;
}
var simulationOnlyReported = false;
var GAME_STATE_IN_MATCH_MAX = -1;
var GAME_STATE_IN_MATCH_MIN = -9;
var GAME_STATE_FINISHED_MIN = 2;
var GAME_STATE_FINISHED_MAX = 7;
var requiredStableSamples = 3;
var candidateSignature = null;
var candidateCount = 0;
var lastSentSignature = null;
var lastSentStateSignature = null;
var lastSentStable = null;
var includeState = false;
var traceMode = false;
var ready = false;
var lastError = null;
function asNumber(value) {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value == null) return 0;
  if (typeof value.toNumber === "function") return value.toNumber();
  if (typeof value.tryField === "function") {
    const underlying = value.tryField("value__");
    if (underlying != null) return asNumber(underlying.value);
  }
  const parsed = Number(value.toString());
  if (!Number.isFinite(parsed)) throw new Error(`not a numeric value: ${value}`);
  return parsed;
}
function readNative(object, offset, kind) {
  const address = object.handle.add(offset);
  if (kind === "u32") return address.readU32();
  if (kind === "bool") return address.readU8() !== 0;
  return address.readU8();
}
function readSlotField(object, name) {
  try {
    const value = object.field(name).value;
    if (typeof value === "number" || typeof value === "boolean" || value != null && typeof value.toNumber === "function") {
      return value;
    }
    if (value != null && typeof value.tryField === "function") {
      const underlying = value.tryField("value__");
      if (underlying != null) return underlying.value;
    }
    const fallback = SLOT_FALLBACKS[name];
    if (fallback != null) return readNative(object, fallback[0], fallback[1]);
    return value;
  } catch (error) {
    const fallback = SLOT_FALLBACKS[name];
    if (fallback == null) throw error;
    return readNative(object, fallback[0], fallback[1]);
  }
}
function readBoolean(object, name) {
  const value = readSlotField(object, name);
  return typeof value === "boolean" ? value : asNumber(value) !== 0;
}
var ENUM_TABLE_CLASSES = [
  "Match3Engine.SlotValueType",
  "Match3Engine.SlotColor",
  "Match3Engine.BoardModelName",
  "Match3Engine.SpecialAbilityType"
];
var cachedEnumTables = null;
var cachedGameVersion = null;
function readEnumTables(image) {
  const tables = {};
  for (const fullName of ENUM_TABLE_CLASSES) {
    let klass = null;
    try {
      klass = image.class(fullName);
    } catch (_) {
      klass = null;
    }
    if (klass == null) continue;
    const table = {};
    for (const field of klass.fields) {
      let name = null;
      try {
        name = field.name;
      } catch (_) {
        continue;
      }
      if (name == null) continue;
      try {
        if (!field.isLiteral) continue;
        table[name] = asNumber(field.value);
      } catch (_) {
      }
    }
    tables[fullName.split(".").pop()] = table;
  }
  return tables;
}
function findAssemblyImage() {
  const preferred = ["Match3Engine", "Match3Engine.dll"];
  for (const name of preferred) {
    const assembly = Il2Cpp.domain.tryAssembly(name);
    if (assembly != null) return assembly.image;
  }
  for (const assembly of Il2Cpp.domain.assemblies) {
    try {
      assembly.image.class("Match3Engine.GameLogic");
      return assembly.image;
    } catch (_) {
    }
  }
  throw new Error("assembly containing Match3Engine.GameLogic was not found");
}
function initializeMetadata() {
  const image = findAssemblyImage();
  gameLogicClass = image.class("Match3Engine.GameLogic");
  boardClass = image.class("Match3Engine.BoardModel");
  try {
    gameDataClass = image.class("Match3Engine.Match3GameData");
  } catch (_) {
    gameDataClass = null;
  }
  slotClass = image.class("Match3Engine.SlotModel");
  try {
    froggyClass = image.class("Match3Engine.FroggyFu");
  } catch (_) {
    froggyClass = null;
  }
  try {
    jellyClass = image.class("Match3Engine.JellySE");
  } catch (_) {
    jellyClass = null;
  }
  const checks = {};
  const descriptors = [
    ["GameLogic.board", gameLogicClass, "board"],
    ["BoardModel.slots", boardClass, "<slots>k__BackingField"],
    ["SlotModel.color", slotClass, "color"],
    ["SlotModel.color2", slotClass, "color2"],
    ["SlotModel.value", slotClass, "value"],
    ["SlotModel.originalValue", slotClass, "originalValue"],
    ["SlotModel.holdValue", slotClass, "holdValue"],
    ["SlotModel.relatedPlayerIndex", slotClass, "relatedPlayerIndex"],
    ["SlotModel.status", slotClass, "status"],
    ["SlotModel.score", slotClass, "score"],
    ["SlotModel.scoreModifierOrigin", slotClass, "scoreModifierOrigin"],
    ["SlotModel.scoreModifierBonus", slotClass, "scoreModifierBonus"],
    ["SlotModel.energy", slotClass, "energy"],
    ["SlotModel.hitPoints", slotClass, "hitPoints"],
    ["SlotModel.origin", slotClass, "origin"]
  ];
  for (const [label, klass, fieldName] of descriptors) {
    try {
      const actual = klass.field(fieldName).offset;
      checks[label] = {
        expected: EXPECTED_OFFSETS[label],
        actual,
        matches: actual === EXPECTED_OFFSETS[label]
      };
    } catch (error) {
      checks[label] = { expected: EXPECTED_OFFSETS[label], error: String(error) };
    }
  }
  const enumStart = Date.now();
  try {
    cachedEnumTables = readEnumTables(image);
  } catch (_) {
    cachedEnumTables = null;
  }
  const enumMilliseconds = Date.now() - enumStart;
  try {
    cachedGameVersion = Il2Cpp.application.version ?? null;
  } catch (_) {
    cachedGameVersion = null;
  }
  send({
    type: "metadata",
    assembly: image.assembly.name,
    offsets: checks,
    game_version: cachedGameVersion,
    enums: cachedEnumTables,
    enum_read_ms: enumMilliseconds
  });
}
function isSimulation(instance) {
  try {
    const field = instance.tryField("isAISimulation");
    if (field != null) {
      const value = field.value;
      if (typeof value === "boolean") return value;
      return asNumber(value) !== 0;
    }
  } catch (_) {
  }
  try {
    return instance.handle.add(EXPECTED_OFFSETS["GameLogic.isAISimulation"]).readU8() !== 0;
  } catch (_) {
    return false;
  }
}
function hasBoard(instance) {
  try {
    const board = instance.field("board").value;
    return board != null && !board.handle.isNull();
  } catch (_) {
    try {
      return !instance.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer().isNull();
    } catch (_2) {
      return false;
    }
  }
}
function isPlayable(instance) {
  return hasBoard(instance) && !isSimulation(instance);
}
function stateIsFinished(instance) {
  const state = readGameStateEnum(instance);
  return state != null && state >= GAME_STATE_FINISHED_MIN;
}
function newerPlayableConstruction() {
  if (cachedGameLogic == null || !useCtorHook) return null;
  if (constructedCount === ringScannedAtCount) return null;
  let sawPending = false;
  for (let i = constructedRing.length - 1; i >= 0; i--) {
    const handle = constructedRing[i];
    if (handle == null || handle.isNull()) continue;
    if (handle.equals(cachedGameLogic.handle)) continue;
    try {
      const candidate = new Il2Cpp.Object(handle);
      if (!hasBoard(candidate)) {
        sawPending = true;
        continue;
      }
      if (isPlayable(candidate) && !stateIsFinished(candidate)) {
        ringScannedAtCount = constructedCount;
        return candidate;
      }
    } catch (_) {
    }
  }
  if (!sawPending) ringScannedAtCount = constructedCount;
  return null;
}
function chooseInstances(klass, why) {
  chooseCount += 1;
  lastChooseWhy = why;
  lastChooseAt = Date.now();
  send({ type: "choose", phase: "begin", why, count: chooseCount, match_active: matchActive });
  const started = Date.now();
  try {
    const instances = Il2Cpp.gc.choose(klass);
    lastChooseMs = Date.now() - started;
    send({
      type: "choose",
      phase: "end",
      why,
      count: chooseCount,
      match_active: matchActive,
      ms: lastChooseMs,
      instances: instances.length
    });
    return instances;
  } catch (error) {
    lastChooseMs = Date.now() - started;
    send({
      type: "choose",
      phase: "end",
      why,
      count: chooseCount,
      match_active: matchActive,
      ms: lastChooseMs,
      error: String(error)
    });
    throw error;
  }
}
function abilityFromPlayers(klass) {
  const logic = cachedGameLogic;
  if (logic == null) return null;
  try {
    for (const control of listItems(fieldValue(logic, "players"), 8)) {
      const ability = fieldValue(control, "ability");
      if (ability == null || ability.class == null) continue;
      if (ability.class.handle.equals(klass.handle) || ability.class.isSubclassOf(klass, false)) {
        return ability;
      }
    }
  } catch (_) {
  }
  return null;
}
function playersBroughtAbility(typeId) {
  const logic = cachedGameLogic;
  if (logic == null) return null;
  let seen = 0;
  try {
    for (const control of listItems(fieldValue(logic, "players"), 8)) {
      const type = fieldNumber(fieldValue(control, "model"), "specialAbilityType");
      if (type == null) continue;
      seen += 1;
      if (type === typeId) return true;
    }
  } catch (_) {
    return null;
  }
  return seen > 0 ? false : null;
}
function abilityChooseAllowed(onBoard, used, after) {
  if (Date.now() < after) return false;
  const budget = onBoard ? ABILITY_CHOOSE_BLIND_PER_MATCH + ABILITY_CHOOSE_HINTED_PER_MATCH : ABILITY_CHOOSE_BLIND_PER_MATCH;
  return used < budget;
}
function resolveGameLogic() {
  if (!matchActive && cachedGameLogic != null && hasBoard(cachedGameLogic) && (isDeadLogic(cachedGameLogic) || isEndedLogic(cachedGameLogic) || stateIsFinished(cachedGameLogic))) {
    const now = Date.now();
    if (now >= pendingMatchUntil && now < idleChooseAfter) return cachedGameLogic;
    cachedGameLogic = null;
  }
  if (matchActive && cachedGameLogic != null && hasBoard(cachedGameLogic) && stateIsFinished(cachedGameLogic)) {
    return cachedGameLogic;
  }
  if (cachedGameLogic != null && hasBoard(cachedGameLogic) && !stateIsFinished(cachedGameLogic)) {
    const fresher = newerPlayableConstruction();
    if (fresher != null) {
      cachedGameLogic = fresher;
      resolveByHook += 1;
      send({
        type: "error",
        stage: "resolve",
        message: "novi GameLogic konstruisan tokom kesirane partije; prelazim na noviju instancu"
      });
    }
    return cachedGameLogic;
  }
  const keptInMatch = matchActive ? cachedGameLogic : null;
  cachedGameLogic = null;
  if (gameLogicClass == null) throw new Error("GameLogic metadata is not initialized");
  if (useCtorHook && constructedHandle != null && !constructedHandle.isNull()) {
    try {
      const candidate = new Il2Cpp.Object(constructedHandle);
      if (isPlayable(candidate) && !stateIsFinished(candidate)) {
        cachedGameLogic = candidate;
        resolveByHook += 1;
        return candidate;
      }
    } catch (_) {
    }
  }
  if (!matchActive && Date.now() < idleChooseAfter && Date.now() >= pendingMatchUntil) {
    deferredResolves += 1;
    throw new Error("GameLogic heap walk deferred (last lobby walk was slow)");
  }
  if (matchActive) {
    const now = Date.now();
    if (inMatchResolveWalks >= IN_MATCH_RESOLVE_WALKS_PER_MATCH || now < inMatchResolveAfter) {
      deferredResolves += 1;
      if (keptInMatch != null) {
        cachedGameLogic = keptInMatch;
        return keptInMatch;
      }
      throw new Error("GameLogic heap walk refused inside the match (budget spent)");
    }
    inMatchResolveWalks += 1;
    inMatchResolveAfter = now + IN_MATCH_RESOLVE_SPACING_MS;
  }
  const walkStarted = Date.now();
  const instances = chooseInstances(gameLogicClass, "GameLogic");
  if (!matchActive) {
    const cost = Date.now() - walkStarted;
    const paced = Math.min(
      IDLE_CHOOSE_MAX_DELAY_MS,
      Math.max(IDLE_STATE_CHECK_MS, cost * IDLE_CHOOSE_COST_FACTOR)
    );
    idleChooseAfter = Date.now() + (Date.now() < pendingMatchUntil ? paced : Math.max(paced, IDLE_WALK_INTERVAL_MS));
  }
  const withBoard = instances.filter(hasBoard);
  resolveByChoose += 1;
  if (withBoard.length === 0) {
    throw new Error(`active Match3Engine.GameLogic not found (${instances.length} heap instances)`);
  }
  const active = withBoard.filter((instance) => !isDeadLogic(instance));
  if (active.length === 0) {
    throw new Error(
      `every GameLogic with a board (${withBoard.length}) belongs to a match that already ended`
    );
  }
  const playing = active.filter((instance) => !isSimulation(instance));
  let chosen = playing.length > 0 ? playing : active;
  let newestIndex = null;
  for (const instance of chosen) {
    const index = readGameIndex(instance);
    if (index != null && (newestIndex == null || index > newestIndex)) newestIndex = index;
  }
  if (newestIndex != null) {
    const newest = chosen.filter((instance) => readGameIndex(instance) === newestIndex);
    if (newest.length > 0) chosen = newest;
  }
  const live = chosen.filter((instance) => !stateIsFinished(instance));
  if (live.length > 0) chosen = live;
  const fresh = chosen.filter((instance) => !isEndedLogic(instance));
  if (fresh.length > 0) chosen = fresh;
  if (playing.length === 0 && !simulationOnlyReported) {
    simulationOnlyReported = true;
    send({
      type: "error",
      stage: "resolve",
      message: `sve GameLogic instance (${active.length}) tvrde da su AI simulacija; igram na poslednjoj`
    });
  }
  cachedGameLogic = chosen[chosen.length - 1];
  return cachedGameLogic;
}
function reviveNewestDeadLogic() {
  if (gameLogicClass == null || deadLogicKeys.size === 0) return null;
  const instances = chooseInstances(gameLogicClass, "GameLogic (ozivljavanje)");
  const candidates = instances.filter(
    (instance) => hasBoard(instance) && !isSimulation(instance) && isDeadLogic(instance) && !stateIsFinished(instance)
  );
  if (candidates.length === 0) return null;
  let chosen = candidates[candidates.length - 1];
  let newestIndex = null;
  for (const instance of candidates) {
    const index = readGameIndex(instance);
    if (index != null && (newestIndex == null || index > newestIndex)) {
      newestIndex = index;
      chosen = instance;
    }
  }
  const key = logicKey(chosen);
  if (key != null) deadLogicKeys.delete(key);
  try {
    if (endedLogicHandle != null && chosen.handle.toString() === endedLogicHandle) {
      endedLogicHandle = null;
    }
  } catch (_) {
  }
  quietSignature = null;
  cachedGameLogic = chosen;
  return chosen;
}
function installCtorHook() {
  if (!useCtorHook || ctorHookState !== "off" || gameLogicClass == null) return;
  try {
    let attached = 0;
    for (const method of gameLogicClass.methods) {
      if (method.name !== ".ctor") continue;
      const address = method.virtualAddress;
      if (address == null || address.isNull()) continue;
      ctorHookListeners.push(Interceptor.attach(address, {
        onEnter(args) {
          constructedHandle = args[0];
          constructedCount += 1;
          constructedRing.push(args[0]);
          if (constructedRing.length > CONSTRUCTED_RING_MAX) {
            constructedRing.shift();
          }
        }
      }));
      attached += 1;
    }
    ctorHookState = attached > 0 ? "on" : "failed";
    if (attached === 0) ctorHookError = "nijedan .ctor nema adresu";
  } catch (error) {
    ctorHookState = "failed";
    ctorHookError = String(error);
  }
}
function removeCtorHook() {
  constructedHandle = null;
  constructedSeen = null;
  constructedRing.length = 0;
  ringScannedAtCount = -1;
  if (ctorHookListeners.length === 0) {
    ctorHookDetachPending = false;
    return;
  }
  if (matchActive) {
    ctorHookDetachPending = true;
    return;
  }
  ctorHookDetachPending = false;
  while (ctorHookListeners.length > 0) {
    const listener = ctorHookListeners.pop();
    try {
      if (listener != null) listener.detach();
    } catch (error) {
      ctorHookError = `detach: ${String(error)}`;
    }
  }
  constructedRing.length = 0;
  constructedHandle = null;
  if (ctorHookState === "on") ctorHookState = "off";
}
function installDisposeHook() {
  if (disposeHookState !== "off" || gameLogicClass == null) return;
  try {
    let attached = 0;
    for (const method of gameLogicClass.methods) {
      if (method.name !== "Dispose" || method.parameterCount !== 0) continue;
      const address = method.virtualAddress;
      if (address == null || address.isNull()) continue;
      Interceptor.attach(address, {
        onEnter(args) {
          disposedHandle = args[0];
          disposedAt = Date.now();
          disposedCount += 1;
        }
      });
      attached += 1;
    }
    disposeHookState = attached > 0 ? "on" : "failed";
    if (attached === 0) disposeHookError = "GameLogic.Dispose nema adresu";
  } catch (error) {
    disposeHookState = "failed";
    disposeHookError = String(error);
  }
}
function readingLogicDisposed() {
  if (disposedHandle == null || cachedGameLogic == null) return false;
  return disposedHandle.equals(cachedGameLogic.handle);
}
function boardObject(logic) {
  try {
    const value = logic.field("board").value;
    if (value == null || value.handle.isNull()) throw new Error("GameLogic.board is null");
    return value;
  } catch (_) {
    const pointer = logic.handle.add(EXPECTED_OFFSETS["GameLogic.board"]).readPointer();
    if (pointer.isNull()) throw new Error("GameLogic.board is null at fallback offset 0xB8");
    return new Il2Cpp.Object(pointer);
  }
}
function readSlot(slot, x, y) {
  return {
    x,
    y,
    row: y,
    col: x,
    color: asNumber(readSlotField(slot, "color")),
    color2: asNumber(readSlotField(slot, "color2")),
    value: asNumber(readSlotField(slot, "value")),
    originalValue: asNumber(readSlotField(slot, "originalValue")),
    holdValue: asNumber(readSlotField(slot, "holdValue")),
    relatedPlayerIndex: asNumber(readSlotField(slot, "relatedPlayerIndex")),
    status: asNumber(readSlotField(slot, "status")),
    score: asNumber(readSlotField(slot, "score")),
    scoreModifierOrigin: asNumber(readSlotField(slot, "scoreModifierOrigin")),
    scoreModifierBonus: asNumber(readSlotField(slot, "scoreModifierBonus")),
    energy: asNumber(readSlotField(slot, "energy")),
    hitPoints: asNumber(readSlotField(slot, "hitPoints")),
    origin: asNumber(readSlotField(slot, "origin")),
    damageable: readBoolean(slot, "damageable"),
    autoDestruct: readBoolean(slot, "autoDestruct"),
    canBeMatched: readBoolean(slot, "canBeMatched"),
    movable: readBoolean(slot, "movable"),
    createdFromCombo: readBoolean(slot, "createdFromCombo"),
    skipDestroyTillMoveEnds: readBoolean(slot, "skipDestroyTillMoveEnds"),
    activateOnHitpointReduced: readBoolean(slot, "activateOnHitpointReduced"),
    isLiveEventPiece: readBoolean(slot, "isLiveEventPiece")
  };
}
function signatureFor(slots) {
  let hash = 2166136261;
  const fields = [
    "color",
    "color2",
    "value",
    "originalValue",
    "holdValue",
    "status",
    "score",
    "scoreModifierBonus",
    "energy",
    "hitPoints",
    "origin"
  ];
  for (const slot of slots) {
    for (const name of fields) {
      let value = Number(slot[name]) >>> 0;
      for (let shift = 0; shift < 32; shift += 8) {
        hash ^= value >>> shift & 255;
        hash = Math.imul(hash, 16777619) >>> 0;
      }
    }
  }
  return hash.toString(16).padStart(8, "0");
}
function asText(value) {
  if (value == null) return null;
  if (typeof value === "string") return value;
  if (typeof value.content === "string") return value.content;
  if (value.handle != null && value.handle.isNull()) return null;
  const text = String(value);
  return text === "null" || text === "undefined" ? null : text;
}
function usable(object) {
  if (object == null) return null;
  if (typeof object !== "object") return object;
  const handle = object.handle;
  if (handle == null) return object;
  return handle.isNull() ? null : object;
}
function callGetter(object, name) {
  const target = usable(object);
  if (target == null) return null;
  try {
    const method = target.tryMethod(name, 0);
    if (method == null) return null;
    return usable(method.invoke());
  } catch (_) {
    return null;
  }
}
function getterNumber(object, name) {
  const value = callGetter(object, name);
  if (value == null) return null;
  try {
    return asNumber(value);
  } catch (_) {
    return null;
  }
}
function getterBoolean(object, name) {
  const value = callGetter(object, name);
  if (value == null) return null;
  if (typeof value === "boolean") return value;
  try {
    return asNumber(value) !== 0;
  } catch (_) {
    return null;
  }
}
function fieldValue(object, name) {
  const target = usable(object);
  if (target == null) return null;
  try {
    const field = target.tryField(name);
    if (field == null) return null;
    const value = field.value;
    return typeof value === "object" ? usable(value) : value;
  } catch (_) {
    return null;
  }
}
function fieldNumber(object, name) {
  const value = fieldValue(object, name);
  if (value == null) return null;
  try {
    return asNumber(value);
  } catch (_) {
    return null;
  }
}
function fieldBoolean(object, name) {
  const value = fieldValue(object, name);
  if (value == null) return null;
  if (typeof value === "boolean") return value;
  try {
    return asNumber(value) !== 0;
  } catch (_) {
    return null;
  }
}
function listItems(list, limit) {
  const target = usable(list);
  if (target == null) return [];
  try {
    const countMethod = target.tryMethod("get_Count", 0);
    const getItem = target.tryMethod("get_Item", 1);
    if (countMethod == null || getItem == null) return [];
    const count = asNumber(countMethod.invoke());
    if (!Number.isFinite(count) || count <= 0) return [];
    const values = [];
    for (let index = 0; index < Math.min(count, limit); index++) {
      values.push(getItem.invoke(index));
    }
    return values;
  } catch (_) {
    return [];
  }
}
function numberList(list, limit = 32) {
  if (usable(list) == null) return null;
  try {
    return listItems(list, limit).map(asNumber);
  } catch (_) {
    return null;
  }
}
function readBoardAbilities(control) {
  const list = fieldValue(control, "BoardAbilities");
  if (usable(list) == null) return null;
  return listItems(list, 8).map((ability) => {
    const config = fieldValue(ability, "<Config>k__BackingField");
    return {
      type: fieldNumber(ability, "<Type>k__BackingField"),
      name: asText(fieldValue(config, "name")),
      index: fieldNumber(config, "index")
    };
  });
}
function readAbilityParams(config) {
  const list = fieldValue(config, "additionalParams");
  if (usable(list) == null) return null;
  const params = {};
  for (const param of listItems(list, 24)) {
    const key = asText(fieldValue(param, "<key>k__BackingField"));
    if (key == null) continue;
    params[key] = String(asText(fieldValue(param, "<value>k__BackingField")));
  }
  return params;
}
var ABILITY_TYPE_MIXY_MEOW = 59;
var ABILITY_TYPE_UFO_SE = 49;
function readAbilityEngineCounters(ability, abilityType) {
  const target = usable(ability);
  if (target == null) return null;
  try {
    if (abilityType === ABILITY_TYPE_MIXY_MEOW) {
      return {
        uses_left: getterNumber(target, "get_UsesLeft"),
        passive_uses_since_activate: getterNumber(
          target,
          "get_NumOfPassiveUsesSinceLastActivate"
        ),
        activates: getterNumber(target, "get_Activates")
      };
    }
    if (abilityType === ABILITY_TYPE_UFO_SE) {
      return {
        remaining_hud_eyes: getterNumber(target, "get_RemainingHudEyes"),
        colors_to_pick: getterNumber(target, "get_colorsToPick"),
        colors_picked: getterNumber(target, "get_ColorsPicked"),
        passive_activates: getterNumber(target, "get_PassiveActivates")
      };
    }
    return null;
  } catch (_) {
    return null;
  }
}
function readPlayer(control, deep = false) {
  const model = fieldValue(control, "model");
  const ability = fieldValue(control, "ability");
  const abilityConfig = fieldValue(ability, "<Config>k__BackingField");
  const abilityType = fieldNumber(model, "specialAbilityType");
  return {
    index: fieldNumber(model, "index"),
    score: fieldNumber(model, "score"),
    turn_score: fieldNumber(model, "turnScore"),
    spawn_bonus: fieldNumber(model, "spawnBonus"),
    max_round_score: fieldNumber(model, "maxRoundScore"),
    rounds_won: fieldNumber(model, "roundsWon"),
    energy: fieldNumber(model, "energy"),
    energy_to_ability: getterNumber(control, "get_EnergyToAbility"),
    energy_full: getterBoolean(control, "get_IsSpecialAbilityEnergyFull"),
    energy_colors: numberList(fieldValue(control, "energyColors")),
    booster_activations_left: null,
    score_multiplier: fieldNumber(model, "scoreMultiplier"),
    health: fieldNumber(model, "health"),
    slot_type: fieldNumber(model, "slotType"),
    bonus_tiles_collected: fieldNumber(model, "bonusTilesCollected"),
    // Which SE booster this player brought, per Match3Engine.SpecialAbilityType.
    special_ability_type: abilityType,
    // SpecialAbility.Config.name is the booster's in-game name, which is
    // what the bot's own booster list is keyed on.
    special_ability_name: asText(fieldValue(abilityConfig, "name")),
    // Description and tuning params describe how this booster behaves. The
    // shipped Constants asset only covers the classic set, so the modern
    // boosters can be learned no other way than from the live model.
    special_ability_description: asText(fieldValue(abilityConfig, "description")),
    special_ability_params: readAbilityParams(abilityConfig),
    // The live SpecialAbility instance, not its config: `activeSpecialAbility
    // Type` on the model is only 49 for the single frame the UFO activation
    // animation runs in, so the host cannot see from it how many eyes are
    // still armed. Whatever counter the ability keeps for that is one of
    // these fields -- a read-only scalar sweep, same as the mutation one.
    special_ability_fields: readAllInstanceFields(ability),
    special_ability_engine: deep ? readAbilityEngineCounters(ability, abilityType) : null,
    ufo_colors_exploded_this_move: deep && abilityType === ABILITY_TYPE_UFO_SE ? intListValues(fieldValue(control, "colorsExplodedThisMove"), 16) : null,
    active_special_ability_type: fieldNumber(model, "activeSpecialAbilityType"),
    // Nine board models return from their hook without applying the mode's
    // own rule when the player spent an ability this move (decoded from
    // libil2cpp.so -- see docs/game_mode_logic_from_code.md). The three
    // fields the engine reads for that decision are plain booleans/enums on
    // PlayerModel at 0xc0 / 0xc2 / 0xc4, so no method call is needed.
    is_ability_used_this_move: fieldBoolean(model, "isAbilityUsedThisMove"),
    is_board_ability_used_this_move: fieldBoolean(
      model,
      "isBoardAbilityUsedThisMove"
    ),
    board_ability_used_this_move: fieldNumber(model, "boardAbilityUsedThisMove"),
    active_board_ability: fieldNumber(model, "activeBoardAbilityType"),
    board_abilities: readBoardAbilities(control),
    is_my_turn: fieldBoolean(control, "<IsMyTurn>k__BackingField"),
    has_played_this_turn: fieldBoolean(model, "HasPlayedThisTurn"),
    // PlayerClientControl.Type (Local/Remote/AI) is the only thing that says
    // which side is us; the player on turn is not necessarily us.
    player_type: fieldNumber(control, "<Type>k__BackingField"),
    // Mutation Lab keeps the picked mutations on the PlayerModel, and the
    // catalogue extracted from the client (docs/game_mode_rules.md) names
    // ~30 mutation types -- far more than it is worth hand-listing here
    // before a single live match has been seen. A sweep answers "what is
    // actually on this player" instead, but PlayerModel is also where the
    // account identifiers live, so it is filtered down to the mutation
    // fields *inside the process*: what is not read cannot leak.
    mutation_fields: readMutationFields(model)
  };
}
var cachedRulesKey = null;
var cachedDirectionsKey = null;
var cachedDirections = null;
var cachedRulesFields = null;
function ruleFieldValue(target, name) {
  const value = fieldValue(target, name);
  if (value == null) return null;
  const kind = typeof value;
  if (kind === "boolean" || kind === "number" || kind === "string") return value;
  let className = null;
  try {
    className = value.class != null ? String(value.class.name) : null;
  } catch (_) {
    className = null;
  }
  if (className === "String") return asText(value);
  try {
    if (typeof value.tryField === "function") {
      const underlying = value.tryField("value__");
      if (underlying != null) {
        const number = Number(underlying.value);
        if (Number.isFinite(number)) return number;
      }
    }
  } catch (_) {
  }
  return className == null ? null : `<${className}>`;
}
var SCALAR_FIELD_TYPES = /* @__PURE__ */ new Set([
  "System.Boolean",
  "System.Byte",
  "System.SByte",
  "System.Int16",
  "System.UInt16",
  "System.Int32",
  "System.UInt32",
  "System.Int64",
  "System.UInt64",
  "System.Single",
  "System.Double",
  "System.String"
]);
function isReadableRuleField(field) {
  try {
    if (field.isStatic || field.isThreadStatic || field.isLiteral) return false;
    const type = field.type;
    if (type == null) return false;
    if (SCALAR_FIELD_TYPES.has(String(type.name))) return true;
    return type.class != null && type.class.isEnum === true;
  } catch (_) {
    return false;
  }
}
function readAllInstanceFields(instance) {
  const target = usable(instance);
  if (target == null) return null;
  const values = {};
  let fields = [];
  try {
    fields = target.class.fields;
  } catch (_) {
    fields = [];
  }
  for (const field of fields) {
    let name = null;
    try {
      name = field.name;
    } catch (_) {
      continue;
    }
    if (name == null || Object.prototype.hasOwnProperty.call(values, name)) continue;
    try {
      if (isReadableRuleField(field)) {
        values[name] = ruleFieldValue(target, name);
      } else {
        let typeName = null;
        try {
          typeName = field.type != null ? String(field.type.name) : null;
        } catch (_) {
          typeName = null;
        }
        const contents = intCollectionValue(target, name, typeName);
        if (contents !== void 0) {
          values[name] = contents;
          if (typeName != null && INT_DICTIONARY_TYPES.has(typeName)) {
            values[`${name}__diag`] = intDictionaryDiag(fieldValue(target, name));
          }
        } else if (typeName != null) {
          values[name] = `<${typeName}>`;
        }
      }
    } catch (_) {
    }
  }
  return values;
}
function readAllRuleFields(rules) {
  const target = usable(rules);
  if (target == null) return null;
  let key = null;
  try {
    key = String(target.handle);
  } catch (_) {
    key = null;
  }
  if (key != null && key === cachedRulesKey) return cachedRulesFields;
  const values = readAllInstanceFields(target);
  cachedRulesKey = key;
  cachedRulesFields = values;
  return values;
}
function readMutationFields(instance) {
  const all = readAllInstanceFields(instance);
  if (all == null) return null;
  const values = {};
  for (const name of Object.keys(all)) {
    if (name.toLowerCase().includes("mutation")) values[name] = all[name];
  }
  return values;
}
function readDirectionTables(board) {
  const target = usable(board);
  if (target == null) return null;
  let key = null;
  try {
    key = String(target.handle);
  } catch (_) {
    key = null;
  }
  if (key != null && key === cachedDirectionsKey) return cachedDirections;
  const tables = {};
  let fields = [];
  try {
    fields = target.class.fields;
  } catch (_) {
    fields = [];
  }
  for (const field of fields) {
    let name = null;
    try {
      name = field.name;
    } catch (_) {
      continue;
    }
    if (name == null || !/directions$/i.test(name)) continue;
    try {
      let array = fieldValue(target, name);
      if (array == null) array = staticFieldValue(target, name);
      if (array == null) {
        tables[name] = "<unreadable>";
        continue;
      }
      const length = Number(array.length);
      if (!Number.isFinite(length) || length <= 0 || length > 256) {
        tables[name] = `<length:${array.length}>`;
        continue;
      }
      const points = [];
      for (let index = 0; index < length; index++) {
        const point = array.get(index);
        const numbers = valueTypeNumbers(point);
        if (numbers != null) points.push(numbers);
      }
      tables[name] = points.length > 0 ? points : { length, element_fields: valueTypeFieldNames(point0(array)) };
    } catch (error) {
      tables[name] = `<error:${String(error)}>`;
    }
  }
  cachedDirectionsKey = key;
  cachedDirections = tables;
  return tables;
}
function listItemsByField(list, limit = 32) {
  const target = usable(list);
  if (target == null) return [];
  try {
    const items = fieldValue(target, "_items");
    const size = Number(fieldValue(target, "_size"));
    if (items == null || !Number.isFinite(size) || size <= 0) return [];
    const values = [];
    for (let index = 0; index < Math.min(size, limit); index++) {
      values.push(items.get(index));
    }
    return values;
  } catch (_) {
    return [];
  }
}
var INT_LIST_TYPE = "System.Collections.Generic.List<System.Int32>";
var ENUM_INT_LIST_TYPES = /* @__PURE__ */ new Set([
  "System.Collections.Generic.List<Match3Engine.SlotColor>"
]);
var INT_DICTIONARY_TYPES = /* @__PURE__ */ new Set([
  "System.Collections.Generic.Dictionary<System.Int32,System.Int32>",
  "System.Collections.Generic.Dictionary<System.Int32, System.Int32>",
  "System.Collections.Generic.Dictionary<Match3Engine.SlotColor,System.Int32>",
  "System.Collections.Generic.Dictionary<Match3Engine.SlotColor, System.Int32>"
]);
function intCollectionValue(target, name, typeName) {
  if (typeName == null) return void 0;
  if (typeName === INT_LIST_TYPE || ENUM_INT_LIST_TYPES.has(typeName)) {
    return intListValues(fieldValue(target, name));
  }
  if (INT_DICTIONARY_TYPES.has(typeName)) {
    return intDictionaryValues(fieldValue(target, name));
  }
  return void 0;
}
function listItemNumber(item) {
  const direct = Number(item);
  if (Number.isFinite(direct)) return direct;
  try {
    if (item != null && typeof item.tryField === "function") {
      const underlying = item.tryField("value__");
      if (underlying != null) {
        const number = Number(underlying.value);
        if (Number.isFinite(number)) return number;
      }
    }
  } catch (_) {
  }
  return null;
}
function intListValues(list, limit = 64) {
  const target = usable(list);
  if (target == null) return null;
  const values = [];
  for (const item of listItemsByField(target, limit)) {
    const number = listItemNumber(item);
    if (number == null) return null;
    values.push(number);
  }
  return values;
}
function intDictionaryValues(dictionary, limit = 64) {
  const target = usable(dictionary);
  if (target == null) return null;
  let entries = null;
  for (const name of ["entries", "_entries"]) {
    const value = fieldValue(target, name);
    if (value != null) {
      entries = value;
      break;
    }
  }
  let count = NaN;
  for (const name of ["count", "_count"]) {
    const field = fieldValue(target, name);
    if (field == null) continue;
    const value = Number(field);
    if (Number.isFinite(value)) {
      count = value;
      break;
    }
  }
  if (!Number.isInteger(count) || count < 0) return null;
  if (count === 0) return {};
  if (entries == null) return null;
  const raw = rawIntDictionaryEntries(entries, count, limit);
  if (raw != null) return raw;
  const values = {};
  let decoded = 0;
  for (let index = 0; index < Math.min(count, limit); index++) {
    let numbers = null;
    try {
      numbers = valueTypeNumbers(entries.get(index));
    } catch (_) {
      numbers = null;
    }
    if (numbers == null) continue;
    decoded++;
    if (numbers.length >= 4) {
      const [hashCode, , key, value] = numbers;
      if (hashCode < 0) continue;
      values[String(key)] = value;
    } else if (numbers.length === 2) {
      values[String(numbers[0])] = numbers[1];
    }
  }
  if (decoded === 0) return null;
  return values;
}
function intDictionaryDiag(dictionary) {
  const target = usable(dictionary);
  if (target == null) return null;
  const diag = {};
  try {
    diag.handle = String(target.handle);
    diag.fields = target.class.fields.filter((field) => !field.isStatic).map((field) => String(field.name));
    for (const name of ["count", "_count", "freeCount", "_freeCount", "freeList", "_freeList", "version", "_version"]) {
      const field = fieldValue(target, name);
      if (field == null) continue;
      const value = Number(field);
      if (Number.isFinite(value)) diag[name.replace(/^_/, "")] = value;
    }
    let entries = null;
    for (const name of ["entries", "_entries"]) {
      const value = fieldValue(target, name);
      if (value != null) {
        entries = value;
        break;
      }
    }
    if (entries == null) {
      diag.entries = null;
      return diag;
    }
    const length = Number(entries.length);
    diag.entries_length = length;
    let base = null;
    try {
      base = entries.elements.handle;
    } catch (_) {
      base = null;
    }
    if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
    const slots = [];
    for (let index = 0; index < Math.min(length, 8); index++) {
      const item = base.add(index * 16);
      slots.push([item.readS32(), item.add(4).readS32(), item.add(8).readS32(), item.add(12).readS32()]);
    }
    diag.raw_slots = slots;
  } catch (error) {
    diag.error = String(error);
  }
  return diag;
}
function rawIntDictionaryEntries(entries, count, limit) {
  try {
    let length = NaN;
    try {
      length = Number(entries.length);
    } catch (_) {
      length = NaN;
    }
    if (!Number.isFinite(length) || length < count) return null;
    let base = null;
    try {
      base = entries.elements.handle;
    } catch (_) {
      base = null;
    }
    if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
    const values = {};
    for (let index = 0; index < Math.min(count, limit); index++) {
      const item = base.add(index * 16);
      const hashCode = item.readS32();
      const next = item.add(4).readS32();
      if (hashCode < 0 || next < -1) continue;
      values[String(item.add(8).readS32())] = item.add(12).readS32();
    }
    return values;
  } catch (_) {
    return null;
  }
}
function boxedValueText(pointer) {
  if (pointer.isNull()) return "";
  const object = new Il2Cpp.Object(pointer);
  let className = "";
  try {
    className = String(object.class.name);
  } catch (_) {
    return "";
  }
  const payload = pointer.add(Il2Cpp.Object.headerSize);
  switch (className) {
    case "String":
      return new Il2Cpp.String(pointer).content ?? "";
    case "Int32":
    case "UInt32":
      return String(payload.readS32());
    case "Int64":
      return String(payload.readS64());
    case "Int16":
    case "UInt16":
      return String(payload.readS16());
    case "Byte":
    case "SByte":
    case "Boolean":
      return String(payload.readU8());
    case "Single":
      return String(payload.readFloat());
    case "Double":
      return String(payload.readDouble());
    default:
      return `<${className}>`;
  }
}
function rawStringDictionaryEntries(entries, count, limit, diag) {
  const values = {};
  try {
    let elementClass = null;
    try {
      elementClass = entries.elementType?.class ?? null;
    } catch (_) {
      elementClass = null;
    }
    if (elementClass == null) {
      try {
        elementClass = entries.class?.type?.class?.elementClass ?? null;
      } catch (_) {
        elementClass = null;
      }
    }
    if (elementClass == null) {
      diag.raw_error = "no element class";
      return values;
    }
    const fields = elementClass.fields.filter(
      (field) => !field.isStatic && !field.isLiteral
    );
    let size = NaN;
    try {
      size = Number(elementClass.arrayElementSize);
    } catch (_) {
      size = NaN;
    }
    if (!Number.isFinite(size) || size <= 0) {
      const extents = fields.map((field) => Number(field.offset) - Il2Cpp.Object.headerSize + 8);
      size = Math.max(...extents, 8);
      size = Math.ceil(size / 8) * 8;
    }
    let base = null;
    try {
      base = entries.elements.handle;
    } catch (_) {
      base = null;
    }
    if (base == null) base = entries.handle.add(Il2Cpp.Array.headerSize);
    diag.raw = {
      size,
      fields: fields.map((field) => `${field.name}@${field.offset}`)
    };
    const keyField = fields.find((field) => field.name === "key") ?? fields[2];
    const valueField = fields.find((field) => field.name === "value") ?? fields[3];
    if (keyField == null || valueField == null) {
      diag.raw_error = "entry layout not recognised";
      return values;
    }
    const keyOffset = Number(keyField.offset) - Il2Cpp.Object.headerSize;
    const valueOffset = Number(valueField.offset) - Il2Cpp.Object.headerSize;
    let read = 0;
    for (let index = 0; index < Math.min(count, limit); index++) {
      try {
        const item = base.add(index * size);
        const keyPointer = item.add(keyOffset).readPointer();
        if (keyPointer.isNull()) continue;
        const key = new Il2Cpp.String(keyPointer).content;
        if (key == null || key === "") continue;
        values[key] = boxedValueText(item.add(valueOffset).readPointer());
        read++;
      } catch (error) {
        if (diag.raw_entry_error == null) diag.raw_entry_error = String(error);
      }
    }
    diag.raw_read = read;
  } catch (error) {
    diag.raw_error = String(error);
  }
  return values;
}
function readStringDictionary(dictionary, limit = 64, diag = null) {
  const target = usable(dictionary);
  if (target == null) {
    if (diag != null) diag.dictionary = "null";
    return null;
  }
  const notes = diag ?? {};
  try {
    notes.dictionary_fields = target.class.fields.filter((field) => !field.isStatic).map((field) => field.name);
  } catch (_) {
  }
  let entries = null;
  for (const name of ["entries", "_entries"]) {
    const value = fieldValue(target, name);
    if (value != null) {
      entries = value;
      notes.entries_field = name;
      break;
    }
  }
  let count = NaN;
  for (const name of ["count", "_count"]) {
    const field = fieldValue(target, name);
    if (field == null) continue;
    const value = Number(field);
    if (Number.isFinite(value)) {
      count = value;
      notes.count_field = name;
      break;
    }
  }
  notes.count = Number.isFinite(count) ? count : null;
  if (entries == null || !Number.isFinite(count)) return null;
  try {
    notes.entries_length = Number(entries.length);
  } catch (_) {
    notes.entries_length = null;
  }
  const values = {};
  let bridgeRead = 0;
  for (let index = 0; index < Math.min(count, limit); index++) {
    try {
      const entry = entries.get(index);
      if (entry == null) continue;
      const fields = valueTypeFields(entry).filter(
        (field) => !field.isStatic && !field.isLiteral
      );
      if (index === 0) notes.entry_fields = fields.map((field) => field.name);
      if (fields.length < 4) continue;
      const key = asText(usable(entry.field(fields[2].name).value));
      if (key == null || key === "") continue;
      const raw = usable(entry.field(fields[3].name).value);
      let text = asText(raw);
      if (text == null && raw != null) {
        try {
          text = boxedValueText(raw.handle);
        } catch (_) {
          text = null;
        }
      }
      values[key] = text == null ? "" : text;
      bridgeRead++;
    } catch (error) {
      if (notes.bridge_entry_error == null) notes.bridge_entry_error = String(error);
      continue;
    }
  }
  notes.bridge_read = bridgeRead;
  if (bridgeRead === 0 && count > 0) {
    const raw = rawStringDictionaryEntries(entries, count, limit, notes);
    for (const key of Object.keys(raw)) values[key] = raw[key];
    notes.source = Object.keys(raw).length > 0 ? "raw" : "empty";
  } else {
    notes.source = "bridge";
  }
  return values;
}
function hasJellyExtraData(values) {
  if (values == null) return false;
  const named = cachedJellyKeys != null ? cachedJellyKeys["all_infected"] : null;
  for (const key of Object.keys(values)) {
    if (named != null && key === named) return true;
    if (JELLY_EXTRA_DATA_HINT.test(key)) return true;
  }
  return false;
}
function extraDataFallbackBoard(board) {
  if (cachedExtraDataBoard != null) {
    try {
      if (!cachedExtraDataBoard.handle.isNull()) return cachedExtraDataBoard;
    } catch (_) {
    }
    cachedExtraDataBoard = null;
  }
  if (cachedJelly == null) return null;
  if (extraDataScanned) return null;
  extraDataScanned = true;
  let fallback = null;
  try {
    const instances = chooseInstances(board.class, "BoardModel extraData");
    for (const instance of instances) {
      try {
        if (instance.handle.equals(board.handle)) continue;
        const owner = extraDataBoardOwner(instance);
        if (owner === "over") continue;
        if (owner === "other" && fallback != null) continue;
        const values = readStringDictionary(
          fieldValue(instance, "extraData")
        );
        if (!hasJellyExtraData(values)) continue;
        if (owner === "current") {
          cachedExtraDataBoard = instance;
          return instance;
        }
        fallback = instance;
      } catch (_) {
        continue;
      }
    }
  } catch (_) {
  }
  if (fallback != null) cachedExtraDataBoard = fallback;
  return fallback;
}
function extraDataBoardOwner(instance) {
  let owner = null;
  try {
    owner = usable(fieldValue(instance, "logic"));
  } catch (_) {
    owner = null;
  }
  if (owner == null || owner.handle == null) return "other";
  const current = cachedGameLogic;
  try {
    if (current != null && owner.handle.equals(current.handle)) return "current";
  } catch (_) {
  }
  try {
    const logic = owner;
    if (isDeadLogic(logic) || isEndedLogic(logic) || stateIsFinished(logic)) return "over";
  } catch (_) {
  }
  return "other";
}
function readActiveMutations(logic) {
  const list = fieldValue(logic, "mutationsActivatedList");
  if (list == null) return null;
  const mutations = [];
  for (const item of listItemsByField(list)) {
    const fields = readAllInstanceFields(item);
    if (fields == null) continue;
    const config = fieldValue(item, "<config>k__BackingField");
    if (config != null) {
      const configFields = readAllInstanceFields(config);
      if (configFields != null) fields["config"] = configFields;
    }
    mutations.push(fields);
  }
  return mutations;
}
function staticFieldValue(instance, name) {
  try {
    const field = instance.class.tryField(name);
    if (field == null) return null;
    const value = field.value;
    return typeof value === "object" ? usable(value) : value;
  } catch (_) {
    return null;
  }
}
function point0(array) {
  try {
    return array.get(0);
  } catch (_) {
    return null;
  }
}
function valueTypeNumbers(value) {
  if (value == null) return null;
  const numbers = [];
  try {
    for (const field of valueTypeFields(value)) {
      if (field.isStatic || field.isLiteral) continue;
      const raw = value.field(field.name).value;
      const number = Number(raw);
      if (!Number.isFinite(number)) return null;
      numbers.push(number);
    }
  } catch (_) {
    return null;
  }
  return numbers.length > 0 ? numbers : null;
}
function valueTypeFieldNames(value) {
  if (value == null) return null;
  try {
    const fields = valueTypeFields(value);
    return fields.length > 0 ? fields.map((field) => `${field.name}:${field.type.name}`) : null;
  } catch (_) {
    return null;
  }
}
function valueTypeFields(value) {
  for (const owner of [value?.type?.class, value?.class]) {
    try {
      const fields = owner?.fields;
      if (fields != null && fields.length > 0) return fields;
    } catch (_) {
    }
  }
  return [];
}
function pointListValues(list, limit = 64) {
  const target = usable(list);
  if (target == null) return null;
  const points = [];
  for (const item of listItemsByField(target, limit)) {
    const numbers = valueTypeNumbers(item);
    if (numbers == null) return null;
    points.push(numbers);
  }
  return points;
}
function resolveFroggy(onBoard) {
  if (cachedFroggy != null) {
    try {
      if (!cachedFroggy.handle.isNull()) return cachedFroggy;
    } catch (_) {
    }
    cachedFroggy = null;
  }
  if (froggyClass == null) return null;
  const owned = abilityFromPlayers(froggyClass);
  if (owned != null) {
    cachedFroggy = owned;
    return cachedFroggy;
  }
  if (!onBoard && playersBroughtAbility(ABILITY_TYPE_FROGGY_FU) === false) return null;
  if (!abilityChooseAllowed(onBoard, froggyChooses, froggyChooseAfter)) return null;
  froggyChooses += 1;
  froggyChooseAfter = Date.now() + ABILITY_CHOOSE_SPACING_MS;
  try {
    const instances = chooseInstances(froggyClass, "FroggyFu");
    if (instances.length === 0) return null;
    cachedFroggy = instances[instances.length - 1];
    return cachedFroggy;
  } catch (_) {
    return null;
  }
}
function readFroggyState(onBoard) {
  const instance = resolveFroggy(onBoard);
  if (instance == null) return null;
  try {
    const moves = [];
    for (const step of listItemsByField(
      fieldValue(instance, "<attractionMoveData>k__BackingField"),
      256
    )) {
      const points = pointListValues(step, 8);
      if (points != null && points.length > 0) moves.push(points);
    }
    return {
      attraction_moves: moves.length > 0 ? moves : null,
      pull_cluster: pointListValues(
        fieldValue(instance, "<currentResolvePullCluster>k__BackingField")
      ),
      stamped_positions: pointListValues(
        fieldValue(instance, "<stampedPositions>k__BackingField")
      ),
      planned_lotuses: pointListValues(
        fieldValue(instance, "plannedLotusPositionsThisActivation")
      ),
      error: null
    };
  } catch (error) {
    cachedFroggy = null;
    return {
      attraction_moves: null,
      pull_cluster: null,
      stamped_positions: null,
      planned_lotuses: null,
      error: String(error)
    };
  }
}
function resolveJelly(onBoard) {
  if (cachedJelly != null) {
    try {
      if (!cachedJelly.handle.isNull()) return cachedJelly;
    } catch (_) {
    }
    cachedJelly = null;
    cachedJellyKeys = null;
  }
  if (jellyClass == null) return null;
  const owned = abilityFromPlayers(jellyClass);
  if (owned != null) {
    cachedJelly = owned;
    cachedJellyKeys = null;
    return cachedJelly;
  }
  if (!onBoard && playersBroughtAbility(ABILITY_TYPE_JELLY_SE) === false) return null;
  if (!abilityChooseAllowed(onBoard, jellyChooses, jellyChooseAfter)) return null;
  jellyChooses += 1;
  jellyChooseAfter = Date.now() + ABILITY_CHOOSE_SPACING_MS;
  try {
    const instances = chooseInstances(jellyClass, "JellySE");
    if (instances.length === 0) return null;
    cachedJelly = instances[instances.length - 1];
    cachedJellyKeys = null;
    return cachedJelly;
  } catch (_) {
    return null;
  }
}
function readJellyKeys(instance) {
  if (cachedJellyKeys != null) return cachedJellyKeys;
  const names = [
    ["all_infected", "get_AllInfectedKey"],
    ["source_cell", "get_SourceCellToInfectedKey"],
    ["target_color", "get_TargetColorKey"],
    ["phase", "get_PhaseKey"],
    ["uses_left", "get_UsesLeftKey"],
    ["total_uses_this_turn", "get_TotalUsesThisTurnKey"]
  ];
  const keys = {};
  let resolved = 0;
  for (const [label, getter2] of names) {
    const text = asText(callGetter(instance, getter2));
    keys[label] = text;
    if (text != null) resolved++;
  }
  if (resolved === 0) return null;
  cachedJellyKeys = keys;
  return keys;
}
function readJellyState(deep, onBoard) {
  const instance = resolveJelly(onBoard);
  if (instance == null) return null;
  try {
    const keys = readJellyKeys(instance);
    let allInfected = null;
    let sourceCell = null;
    if (deep) {
      allInfected = pointListValues(callGetter(instance, "get_AllInfected"));
      sourceCell = pointListValues(
        callGetter(instance, "get_SourceCellToInfected")
      );
    }
    return {
      keys,
      all_infected: allInfected,
      source_cell: sourceCell,
      conversion_point: valueTypeNumbers(
        fieldValue(instance, "ConversionPoint")
      ),
      verified: deep && allInfected != null,
      error: null
    };
  } catch (error) {
    cachedJelly = null;
    cachedJellyKeys = null;
    return {
      keys: null,
      all_infected: null,
      source_cell: null,
      conversion_point: null,
      verified: false,
      error: String(error)
    };
  }
}
function readCellMultipliers(board, rows, columns) {
  const target = usable(board);
  if (target == null) return null;
  let getCell = null;
  try {
    getCell = target.method("GetCell", 2);
  } catch (_) {
    return null;
  }
  if (getCell == null) return null;
  const multipliers = [];
  for (let x = 0; x < columns; x++) {
    let best = null;
    for (let y = 0; y < rows; y++) {
      let value = null;
      try {
        const cell = getCell.invoke(x, y);
        value = fieldNumber(cell, "scoreMultiplier");
      } catch (_) {
        value = null;
      }
      if (value == null || !Number.isFinite(value)) continue;
      if (best == null || value > best) best = value;
    }
    if (best == null) return null;
    multipliers.push(best);
  }
  return multipliers;
}
var CELL_TYPE_BOARD_MODELS = /* @__PURE__ */ new Set([10, 12]);
function readCellTypes(board, rows, columns) {
  const target = usable(board);
  if (target == null) return null;
  let getCell = null;
  try {
    getCell = target.method("GetCell", 2);
  } catch (_) {
    return null;
  }
  if (getCell == null) return null;
  const grid = [];
  for (let y = 0; y < rows; y++) {
    const row = [];
    for (let x = 0; x < columns; x++) {
      let value = null;
      try {
        const cell = getCell.invoke(x, y);
        value = listItemNumber(cell.field("cellType").value);
      } catch (_) {
        value = null;
      }
      if (value == null || !Number.isFinite(value)) return null;
      row.push(value);
    }
    grid.push(row);
  }
  return grid;
}
function readBoardFields(board) {
  return readAllInstanceFields(board);
}
function readRules(logic) {
  const rules = fieldValue(logic, "gameRules");
  if (rules == null) return null;
  return {
    id: asText(fieldValue(rules, "id")),
    title: asText(fieldValue(rules, "title")),
    board_model_name: fieldNumber(rules, "boardModelName"),
    pvp_mode: fieldNumber(rules, "pvpMode"),
    rumble_type: fieldNumber(rules, "rumbleType"),
    board_size: fieldNumber(rules, "boardSize"),
    colors_count: fieldNumber(rules, "colorsCount"),
    moves_per_turn: fieldNumber(rules, "movesPerTurn"),
    additional_moves: fieldNumber(rules, "additionalMoves"),
    turns_per_game: fieldNumber(rules, "turnsPerGame"),
    time_per_turn: fieldNumber(rules, "timePerTurn"),
    is_timer: fieldBoolean(rules, "isTimer"),
    extra_move_enabled: fieldBoolean(rules, "extraMoveEnabled"),
    energy_mult: fieldNumber(rules, "energyMult"),
    // Score multiplier for every cell a special's blast or a merge swap
    // destroys (GameLogic.CalculateDestructionScoreAndMeter).
    special_combo_score_multiplier: fieldNumber(rules, "specialComboScoreMultiplier"),
    both_colors_charge_energy: fieldBoolean(rules, "bothColorsChargeEnergy"),
    explosion_on_match: fieldBoolean(rules, "explosionOnMatch"),
    destroy_row_on_horizontal_match: fieldBoolean(rules, "destroyRowOnHorizontalMatch"),
    destroy_column_on_vertical_match: fieldBoolean(rules, "destroyColumnOnVerticalMatch"),
    vertical_match_increase_multiplier: fieldBoolean(rules, "verticalMatchIncreaseMultiplier"),
    vertical_match_destroy_color: fieldBoolean(rules, "verticalMatchDestroyColor"),
    specials_auto_explode: fieldBoolean(rules, "specialsAutoExplode"),
    all_specials_lightning: fieldBoolean(rules, "allSpecialsLightning"),
    // "Every match creates a special piece" (Special O'Rama) and the
    // chance-based variant of the same idea.
    every_match_is_special: fieldBoolean(rules, "everyMatchIsSpecial"),
    match_creates_special_chance: fieldNumber(rules, "matchCreatesSpecialChance"),
    bigger_bomb_area: fieldBoolean(rules, "biggerBombArea"),
    ability_locked: fieldBoolean(rules, "abilityLocked"),
    reshuffle_every_turn: fieldBoolean(rules, "reshuffleEveryTurn"),
    solo_refill_mode: fieldBoolean(rules, "soloRefillMode"),
    solo_targets: numberList(fieldValue(rules, "soloTargets")),
    rumble_players_amount: fieldNumber(rules, "rumblePlayersAmount"),
    // Square (2x2) matching is a computed rule, not a stored field.
    is_square_match: getterBoolean(rules, "get_IsInSquareMatchMode"),
    color_combo_energy: intDictionaryValues(fieldValue(rules, "colorComboEnergy")),
    color_energy_override: intDictionaryValues(fieldValue(rules, "_colorEnergyOverride")),
    engine_fields: readAllRuleFields(rules)
  };
}
function readRemainingTime(logic) {
  const rules = fieldValue(logic, "gameRules");
  if (rules == null || fieldBoolean(rules, "isTimer") !== true) return null;
  if (fieldValue(logic, "turnTimer") == null) return null;
  const seconds = getterNumber(logic, "get_RemainingTime");
  if (seconds == null || !Number.isFinite(seconds)) return null;
  return Math.max(0, seconds);
}
function readGameState(logic, deep = false) {
  const players = listItems(fieldValue(logic, "players"), 8).map(
    (control) => readPlayer(control, deep)
  );
  const currentPlayerIndex = fieldNumber(logic, "currentPlayerIndex");
  const opponentIndex = players.length === 2 && currentPlayerIndex != null ? players.length - 1 - currentPlayerIndex : null;
  const chargingColors = players.filter((player) => player.index === currentPlayerIndex).map((player) => player.energy_colors)[0];
  return {
    game_state: fieldNumber(logic, "currentGameState"),
    is_active: null,
    is_singleplayer_board: getterBoolean(logic, "get_IsSingleplayerBoard"),
    moves: fieldNumber(logic, "moves"),
    moves_made_this_turn: fieldNumber(logic, "<MovesMadeThisTurn>k__BackingField"),
    chain_reaction: fieldNumber(logic, "<ChainReaction>k__BackingField"),
    current_turn: fieldNumber(logic, "<Turns>k__BackingField"),
    turns: fieldNumber(logic, "<Turns>k__BackingField"),
    turns_total: fieldNumber(logic, "<TurnsTotal>k__BackingField"),
    current_round: getterNumber(logic, "get_CurrentRound"),
    rounds: getterNumber(logic, "get_Rounds"),
    rounds_total: getterNumber(logic, "get_RoundsTotal"),
    accumulated_move_score: null,
    accumulated_turn_score: fieldNumber(logic, "<AccumulatedTurnScore>k__BackingField"),
    remaining_time: readRemainingTime(logic),
    // A plain byte read (rva 0x573e628); the turn clock stops for popups
    // and reconnects, and a paused countdown must not be treated as time
    // running out.
    timer_paused: getterBoolean(logic, "get_TimerPaused"),
    current_player_index: currentPlayerIndex,
    opponent_index: opponentIndex,
    energy_charging_colors: chargingColors == null ? null : chargingColors,
    opponent_energy_charging_colors: null,
    players,
    rules: readRules(logic)
  };
}
function stateSignatureFor(state) {
  if (state == null) return "00000000";
  const parts = [
    state.game_state,
    state.moves,
    state.moves_made_this_turn,
    state.current_turn,
    state.current_round,
    state.current_player_index
  ];
  for (const player of state.players) {
    parts.push(
      player.index,
      player.score,
      player.turn_score,
      player.energy,
      player.energy_to_ability,
      player.rounds_won,
      player.score_multiplier,
      player.is_my_turn ? 1 : 0
    );
  }
  let hash = 2166136261;
  for (const part of parts) {
    let value = Number(part == null ? 65535 : part) >>> 0;
    for (let shift = 0; shift < 32; shift += 8) {
      hash ^= value >>> shift & 255;
      hash = Math.imul(hash, 16777619) >>> 0;
    }
  }
  return hash.toString(16).padStart(8, "0");
}
var cachedExtras = null;
var cachedExtrasKey = null;
var cachedExtrasAt = 0;
var EXTRAS_MAX_AGE_MS = 1e3;
var COLUMN_MANIA_BOARD_MODEL = 32;
var cachedBoardModel = null;
var cachedBoardModelKey = null;
function boardModelId(logic) {
  let key = null;
  try {
    key = String(logic.handle);
  } catch (_) {
    key = null;
  }
  if (key != null && key === cachedBoardModelKey) return cachedBoardModel;
  let value = null;
  try {
    const rules = fieldValue(logic, "gameRules");
    value = rules == null ? null : fieldNumber(rules, "boardModelName");
  } catch (_) {
    value = null;
  }
  if (value == null) return null;
  cachedBoardModelKey = key;
  cachedBoardModel = value;
  return value;
}
function turnKeyFor(logic) {
  const parts = [];
  for (const name of [
    "moves",
    "<MovesMadeThisTurn>k__BackingField",
    "<ChainReaction>k__BackingField",
    "<Turns>k__BackingField",
    "currentPlayerIndex"
  ]) {
    let value = null;
    try {
      value = fieldNumber(logic, name);
    } catch (_) {
      value = null;
    }
    parts.push(value);
  }
  return parts.join(",");
}
var LAVA_VIEW_CLASS = "match3.board.SpeacialBoards.LavaBackground";
var LAVA_BOARD_CLASS = "FloorIsLavaBoard";
var lavaViewClass = void 0;
var cachedLavaView = null;
var cachedLavaViewFor = null;
var lavaViewChosenFor = null;
function resolveLavaViewClass() {
  if (lavaViewClass !== void 0) return lavaViewClass;
  lavaViewClass = null;
  try {
    lavaViewClass = Il2Cpp.domain.assembly("Assembly-CSharp").image.class(LAVA_VIEW_CLASS);
  } catch (_) {
    lavaViewClass = null;
  }
  return lavaViewClass;
}
function lavaViewFor(board, diag) {
  const boardKey = String(board.handle);
  if (cachedLavaView != null && cachedLavaViewFor === boardKey) {
    diag.found_via = "cache";
    return cachedLavaView;
  }
  cachedLavaView = null;
  cachedLavaViewFor = null;
  const subscribed = {};
  for (const name of ["OnBreak", "OnEruption", "OnReset"]) {
    try {
      const handler = usable(fieldValue(board, name));
      subscribed[name] = handler != null;
      if (handler == null) continue;
      const target = usable(fieldValue(handler, "m_target"));
      if (target != null && String(target.class.name) === "LavaBackground") {
        cachedLavaView = target;
        cachedLavaViewFor = boardKey;
        diag.found_via = `delegate:${name}`;
        diag.played_board_subscribed = subscribed;
        return target;
      }
    } catch (_) {
    }
  }
  diag.played_board_subscribed = subscribed;
  if (lavaViewChosenFor === boardKey) {
    diag.found_via = "none (walk already done for this board)";
    return null;
  }
  lavaViewChosenFor = boardKey;
  const klass = resolveLavaViewClass();
  if (klass == null) {
    diag.found_via = "none (LavaBackground class not resolved)";
    return null;
  }
  try {
    const instances = chooseInstances(klass, "LavaBackground");
    diag.view_instances = instances.length;
    for (let index = instances.length - 1; index >= 0; index--) {
      if (usable(fieldValue(instances[index], "_board")) != null) {
        cachedLavaView = instances[index];
        cachedLavaViewFor = boardKey;
        diag.found_via = "heap walk";
        return cachedLavaView;
      }
    }
  } catch (error) {
    diag.walk_error = String(error);
  }
  diag.found_via = "none";
  return null;
}
function readLavaView(board) {
  let className = "";
  try {
    className = String(board.class.name);
  } catch (_) {
    return null;
  }
  if (className !== LAVA_BOARD_CLASS) return null;
  const diag = { played_board: String(board.handle) };
  try {
    const view = lavaViewFor(board, diag);
    if (view == null) return diag;
    const viewBoard = usable(fieldValue(view, "_board"));
    if (viewBoard == null) {
      diag.view_board = null;
      return diag;
    }
    diag.view_board = String(viewBoard.handle);
    diag.same_board = viewBoard.handle.equals(board.handle);
    const dictionary = fieldValue(viewBoard, "ColumnsEruptionDictionary");
    diag.columns = intDictionaryValues(dictionary);
    diag.columns_diag = intDictionaryDiag(dictionary);
    try {
      diag.extra_data = readStringDictionary(fieldValue(viewBoard, "extraData"), 32);
    } catch (_) {
      diag.extra_data = null;
    }
  } catch (error) {
    diag.error = String(error);
  }
  return diag;
}
function readSnapshotExtras(logic, board, rows, columns, signature, fresh) {
  const now = Date.now();
  let key = null;
  try {
    key = `${board.handle}|${signature}|${turnKeyFor(logic)}`;
  } catch (_) {
    key = null;
  }
  if (!fresh && key != null && cachedExtras != null && key === cachedExtrasKey && now - cachedExtrasAt < EXTRAS_MAX_AGE_MS) {
    return cachedExtras;
  }
  let boardFields = null;
  try {
    boardFields = readBoardFields(board);
  } catch (_) {
    boardFields = null;
  }
  if (boardFields != null) {
    try {
      const lavaView = readLavaView(board);
      if (lavaView != null) {
        boardFields.lava_view = lavaView;
        if (lavaView.same_board === false && lavaView.columns != null) {
          boardFields.ColumnsEruptionDictionary__played = boardFields.ColumnsEruptionDictionary ?? null;
          boardFields.ColumnsEruptionDictionary = lavaView.columns;
        }
      }
    } catch (_) {
    }
  }
  let boardDirections = null;
  try {
    boardDirections = readDirectionTables(board);
  } catch (_) {
    boardDirections = null;
  }
  let cellMultipliers = null;
  const model = boardModelId(logic);
  if (model == null || model === COLUMN_MANIA_BOARD_MODEL) {
    try {
      cellMultipliers = readCellMultipliers(board, rows, columns);
    } catch (_) {
      cellMultipliers = null;
    }
  }
  let cellTypes = null;
  if (model != null && CELL_TYPE_BOARD_MODELS.has(model)) {
    try {
      cellTypes = readCellTypes(board, rows, columns);
    } catch (_) {
      cellTypes = null;
    }
  }
  let mutationFields = null;
  try {
    mutationFields = readMutationFields(logic);
  } catch (_) {
    mutationFields = null;
  }
  let activeMutations = null;
  try {
    activeMutations = readActiveMutations(logic);
  } catch (_) {
    activeMutations = null;
  }
  let boardExtraData = null;
  let boardExtraDataDiag = null;
  try {
    boardExtraDataDiag = {};
    boardExtraData = readStringDictionary(
      fieldValue(board, "extraData"),
      64,
      boardExtraDataDiag
    );
  } catch (error) {
    boardExtraData = null;
    boardExtraDataDiag = { error: String(error) };
  }
  if (boardExtraData == null || Object.keys(boardExtraData).length === 0) {
    const fallback = extraDataFallbackBoard(board);
    if (fallback != null) {
      try {
        const values = readStringDictionary(
          fieldValue(fallback, "extraData")
        );
        if (values != null && Object.keys(values).length > 0) {
          boardExtraData = values;
        }
      } catch (_) {
      }
    }
  }
  const extras = {
    board_fields: boardFields,
    board_directions: boardDirections,
    cell_multipliers: cellMultipliers,
    cell_types: cellTypes,
    mutation_fields: mutationFields,
    active_mutations: activeMutations,
    board_extra_data: boardExtraData,
    board_extra_data_diag: boardExtraDataDiag
  };
  cachedExtras = extras;
  cachedExtrasKey = key;
  cachedExtrasAt = now;
  return extras;
}
function buildSnapshot(reason, stable) {
  const logic = resolveGameLogic();
  const board = boardObject(logic);
  let rows = 7;
  let columns = 7;
  try {
    rows = asNumber(board.field("<Rows>k__BackingField").value);
  } catch (_) {
  }
  try {
    columns = asNumber(board.field("<Columns>k__BackingField").value);
  } catch (_) {
  }
  if (rows !== columns || rows < 4 || rows > 12) {
    throw new Error(`active board is ${columns}x${rows}, expected a square 4..12`);
  }
  const getItem = board.method("get_Item", 2);
  const slots = [];
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < columns; x++) {
      const slot = getItem.invoke(x, y);
      if (slot == null || slot.handle.isNull()) {
        throw new Error(`BoardModel.get_Item(${x},${y}) returned null`);
      }
      slots.push(readSlot(slot, x, y));
    }
  }
  const signature = signatureFor(slots);
  const extras = readSnapshotExtras(
    logic,
    board,
    rows,
    columns,
    signature,
    reason !== "stable_poll" && reason !== "trace_poll"
  );
  const boardExtraData = extras.board_extra_data;
  const now = Date.now();
  const deepJelly = reason === "manual_rpc";
  if (deepJelly) jellyDeepAfter = now + JELLY_DEEP_INTERVAL_MS;
  let jellyOnBoard = false;
  if (boardExtraData != null) {
    for (const key of Object.keys(boardExtraData)) {
      if (JELLY_EXTRA_DATA_HINT.test(key)) {
        jellyOnBoard = true;
        break;
      }
    }
  }
  let jelly = null;
  try {
    jelly = readJellyState(deepJelly, jellyOnBoard);
  } catch (_) {
    jelly = null;
  }
  const lotusOnBoard = slots.some((slot) => slot.value === FROGGY_LOTUS_SLOT_VALUE);
  let state = null;
  let stateError = null;
  if (includeState) {
    try {
      state = readGameState(logic, deepJelly);
    } catch (error) {
      stateError = String(error);
    }
  }
  return {
    schema_version: 4,
    type: "board_snapshot",
    captured_at: (/* @__PURE__ */ new Date()).toISOString(),
    reason,
    stable,
    rows,
    columns,
    game_logic: logic.handle.toString(),
    board_object: board.handle.toString(),
    board_fields: extras.board_fields,
    board_directions: extras.board_directions,
    cell_multipliers: extras.cell_multipliers,
    cell_types: extras.cell_types,
    mutation_fields: extras.mutation_fields,
    active_mutations: extras.active_mutations,
    board_extra_data: boardExtraData,
    board_extra_data_diag: extras.board_extra_data_diag,
    jelly,
    froggy: readFroggyState(lotusOnBoard),
    signature,
    state_signature: stateSignatureFor(state),
    slots,
    state,
    state_error: stateError,
    game_version: cachedGameVersion,
    enums: cachedEnumTables
  };
}
function sendSnapshot(snapshot, force) {
  const unchanged = snapshot.signature === lastSentSignature && snapshot.state_signature === lastSentStateSignature && snapshot.stable === lastSentStable;
  if (!force && unchanged) return false;
  lastSentSignature = snapshot.signature;
  lastSentStateSignature = snapshot.state_signature;
  lastSentStable = snapshot.stable;
  send({ type: "board_snapshot", snapshot });
  return true;
}
function pollOnce() {
  try {
    const snapshot = buildSnapshot("stable_poll", false);
    lastError = null;
    consecutivePollErrors = 0;
    if (snapshot.signature !== candidateSignature) lastChangeTimestamp = Date.now();
    if (snapshot.signature === candidateSignature) {
      candidateCount += 1;
    } else {
      candidateSignature = snapshot.signature;
      candidateCount = 1;
    }
    if (candidateCount >= requiredStableSamples) {
      snapshot.stable = true;
      if (sendSnapshot(snapshot, false)) lastChangeTimestamp = Date.now();
    } else if (traceMode) {
      snapshot.reason = "trace_poll";
      sendSnapshot(snapshot, false);
    }
  } catch (error) {
    const message = String(error);
    candidateSignature = null;
    candidateCount = 0;
    consecutivePollErrors += 1;
    if (message !== lastError) {
      lastError = message;
      send({ type: "error", stage: "poll", message });
    }
  }
}
function readGameCount() {
  if (gameLogicClass == null) return null;
  try {
    const field = gameLogicClass.tryField("GameCount");
    return field == null ? null : asNumber(field.value);
  } catch (_) {
    return null;
  }
}
function readGameStateEnum(logic) {
  const plausible = (value) => value != null && Number.isInteger(value) && value >= GAME_STATE_IN_MATCH_MIN && value <= GAME_STATE_FINISHED_MAX ? value : null;
  try {
    const native = plausible(
      logic.handle.add(EXPECTED_OFFSETS["GameLogic.currentGameState"]).readS32()
    );
    if (native != null) return native;
  } catch (_) {
  }
  try {
    const field = logic.tryField("currentGameState");
    return field == null ? null : plausible(asNumber(field.value));
  } catch (_) {
    return null;
  }
}
function matchIsRunning() {
  let logic;
  try {
    logic = resolveGameLogic();
  } catch (_) {
    return false;
  }
  if (isDeadLogic(logic)) return false;
  const state = readGameStateEnum(logic);
  if (state != null && state >= GAME_STATE_FINISHED_MIN) return false;
  if (quietSignature == null) return true;
  try {
    const moved = buildSnapshot("idle_recheck", false).signature !== quietSignature;
    if (moved) quietSignature = null;
    return moved;
  } catch (_) {
    return false;
  }
}
function stateSaysInMatch() {
  try {
    const logic = resolveGameLogic();
    if (isEndedLogic(logic) || isDeadLogic(logic)) return false;
    const state = readGameStateEnum(logic);
    return state != null && state <= GAME_STATE_IN_MATCH_MAX && state >= GAME_STATE_IN_MATCH_MIN;
  } catch (_) {
    return false;
  }
}
function liveFingerprint(logic) {
  let clock = null;
  try {
    const seconds = readRemainingTime(logic);
    clock = seconds == null ? null : Math.round(seconds * 10);
  } catch (_) {
    clock = null;
  }
  return JSON.stringify([
    fieldNumber(logic, "currentGameState"),
    fieldNumber(logic, "moves"),
    fieldNumber(logic, "<MovesMadeThisTurn>k__BackingField"),
    fieldNumber(logic, "<Turns>k__BackingField"),
    fieldNumber(logic, "currentPlayerIndex"),
    fieldNumber(logic, "<AccumulatedTurnScore>k__BackingField"),
    clock
  ]);
}
function startAttachProbe() {
  const logic = cachedGameLogic;
  if (logic == null) return;
  let print = "";
  try {
    print = liveFingerprint(logic);
  } catch (_) {
    print = "";
  }
  attachProbe = { key: logicKey(logic), print };
  send({
    type: "match_pending",
    reason: "attach_probe",
    note: "partija na heapu, cekam znak zivota (ili Auto / dugme za potez)",
    state: readGameStateEnum(logic)
  });
}
function attachProbeSaysLive() {
  const probe = attachProbe;
  const logic = cachedGameLogic;
  if (probe == null) return true;
  if (logic == null) return false;
  if (logicKey(logic) !== probe.key) return true;
  try {
    return liveFingerprint(logic) !== probe.print;
  } catch (_) {
    return false;
  }
}
function setMatchActive(active, reason) {
  if (matchActive === active) return;
  matchActive = active;
  if (active) attachProbe = null;
  let endedKey = null;
  let dead = false;
  if (active) {
    if (cachedGameLogic != null && isEndedLogic(cachedGameLogic)) endedLogicHandle = null;
  } else if (cachedGameLogic != null) {
    endedKey = logicKey(cachedGameLogic);
    dead = !SOFT_END_REASONS.has(reason);
    if (dead) {
      markLogicDead(endedKey);
    } else {
      try {
        endedLogicHandle = cachedGameLogic.handle.toString();
      } catch (_) {
        endedLogicHandle = null;
      }
    }
  }
  if (!active) {
    idleChooseAfter = Date.now() + IDLE_WALK_INTERVAL_MS;
  }
  cachedGameLogic = active ? cachedGameLogic : null;
  concededAt = null;
  disposedHandle = null;
  disposedAt = null;
  candidateSignature = null;
  candidateCount = 0;
  consecutivePollErrors = 0;
  lastChangeTimestamp = Date.now();
  cachedExtras = null;
  cachedExtrasKey = null;
  cachedBoardModel = null;
  cachedBoardModelKey = null;
  if (active) {
    let handle = null;
    try {
      handle = cachedGameLogic == null ? null : cachedGameLogic.handle.toString();
    } catch (_) {
      handle = null;
    }
    if (handle == null || handle !== budgetMatchHandle) {
      budgetMatchHandle = handle;
      froggyChooses = 0;
      froggyChooseAfter = 0;
      jellyChooses = 0;
      jellyChooseAfter = 0;
      inMatchResolveWalks = 0;
      inMatchResolveAfter = 0;
      cachedExtraDataBoard = null;
      extraDataScanned = false;
    }
  }
  heartbeatAfter = 0;
  if (active) {
    quietSignature = null;
    pendingMatchUntil = 0;
    pendingSince = null;
  } else {
    lastSentSignature = null;
    lastSentStateSignature = null;
    lastSentStable = null;
    cachedFroggy = null;
    cachedJelly = null;
    cachedJellyKeys = null;
    cachedLavaView = null;
    cachedLavaViewFor = null;
    lavaViewChosenFor = null;
    if (ctorHookDetachPending) removeCtorHook();
  }
  send({
    type: "match_state",
    active,
    reason,
    game_count: lastGameCount,
    poll_milliseconds: active ? pollMilliseconds : idleMilliseconds,
    // For the host to persist: the logic this match ended on, and whether
    // the end is final (see deadLogicKeys / markDead).
    logic_key: endedKey,
    dead
  });
  startPolling();
}
function idleOnce() {
  const count = readGameCount();
  if (count == null) return;
  const previous = lastGameCount;
  lastGameCount = count;
  if (count <= 0) return;
  const now = Date.now();
  if (previous != null && count > previous) {
    pendingMatchUntil = now + PENDING_MATCH_MS;
    pendingSince = now;
    idleChooseAfter = 0;
    stateCheckAfter = 0;
    send({
      type: "match_pending",
      reason: "game_count",
      game_count: count,
      previous
    });
  }
  if (useCtorHook && constructedHandle != null) {
    const seen = constructedHandle.toString();
    if (seen !== constructedSeen) {
      constructedSeen = seen;
      if (previous != null) pendingMatchUntil = now + PENDING_MATCH_MS;
    }
  }
  if (previous == null) {
    if (stateSaysInMatch()) startAttachProbe();
    stateCheckAfter = now + IDLE_STATE_CHECK_MS;
    return;
  }
  if (now >= stateCheckAfter) {
    stateCheckAfter = now + IDLE_STATE_CHECK_MS;
    if (stateSaysInMatch()) {
      if (!attachProbeSaysLive()) return;
      const reason = attachProbe != null ? "vec u partiji" : "stanje igre";
      pendingMatchUntil = 0;
      pendingSince = null;
      setMatchActive(true, reason);
      return;
    }
  }
  if (now < pendingMatchUntil) {
    if (matchIsRunning()) {
      pendingMatchUntil = 0;
      setMatchActive(true, "game_count");
    }
    return;
  }
  if (pendingSince != null) {
    pendingSince = null;
    let detail = {};
    try {
      const logic = resolveGameLogic();
      detail = {
        state: readGameStateEnum(logic),
        has_board: hasBoard(logic),
        simulation: isSimulation(logic)
      };
    } catch (error) {
      detail = { resolve_error: String(error) };
    }
    send({
      type: "match_pending_failed",
      game_count: count,
      waited_ms: PENDING_MATCH_MS,
      deferred_resolves: deferredResolves,
      ...detail
    });
  }
  if (quietSignature == null) return;
  if (now < recheckAfter) return;
  recheckAfter = now + IDLE_RECHECK_MS;
  if (matchIsRunning()) setMatchActive(true, "partija se nastavila");
}
function matchEnded() {
  if (cachedGameLogic != null) {
    if (isDeadLogic(cachedGameLogic)) return "partija iz prethodne sesije";
    const cachedState = readGameStateEnum(cachedGameLogic);
    if (cachedState != null && cachedState >= GAME_STATE_FINISHED_MIN) return "partija zavrsena";
  }
  if (concededAt != null) return "predaja";
  if (readingLogicDisposed()) return "partija napustena";
  if (consecutivePollErrors >= 10) return "nema table";
  let logic;
  try {
    logic = resolveGameLogic();
  } catch (_) {
    return "GameLogic je nestao";
  }
  const state = readGameStateEnum(logic);
  if (state != null && state >= GAME_STATE_FINISHED_MIN) return "partija zavrsena";
  if (idleAfterQuietMs > 0 && Date.now() - lastChangeTimestamp > idleAfterQuietMs) {
    return "tabla se ne menja";
  }
  return null;
}
var quietSignature = null;
function tick() {
  const started = Date.now();
  try {
    tickBody();
  } finally {
    lastTickMs = Date.now() - started;
    if (lastTickMs > maxTickMs) maxTickMs = lastTickMs;
    sendHeartbeat();
  }
}
function sendHeartbeat() {
  const now = Date.now();
  if (now < heartbeatAfter) return;
  heartbeatAfter = now + (matchActive ? HEARTBEAT_ACTIVE_MS : HEARTBEAT_IDLE_MS);
  send({
    type: "heartbeat",
    match_active: matchActive,
    tick_ms: lastTickMs,
    max_tick_ms: maxTickMs,
    poll_milliseconds: matchActive ? pollMilliseconds : idleMilliseconds,
    chooses: chooseCount,
    last_choose_why: lastChooseWhy,
    last_choose_ms: lastChooseMs,
    last_choose_ago_ms: lastChooseAt == null ? null : now - lastChooseAt,
    constructed: constructedCount,
    disposed: disposedCount,
    resolve_by_hook: resolveByHook,
    resolve_by_choose: resolveByChoose,
    deferred_resolves: deferredResolves
  });
  maxTickMs = 0;
}
function tickBody() {
  if (!matchActive) {
    idleOnce();
    return;
  }
  pollOnce();
  const count = readGameCount();
  if (count != null && lastGameCount != null && count > lastGameCount) {
    quietSignature = null;
    setMatchActive(false, "nova partija je pocela");
    return;
  }
  const ended = matchEnded();
  if (ended == null) return;
  quietSignature = ended === "partija zavrsena" ? null : lastSentSignature;
  setMatchActive(false, ended);
}
function startPolling() {
  if (pollTimer != null) clearInterval(pollTimer);
  const interval = matchActive ? pollMilliseconds : idleMilliseconds;
  pollTimer = setInterval(() => Il2Cpp.perform(tick), interval);
}
function performAsync(block) {
  return new Promise((resolve, reject) => {
    Il2Cpp.perform(() => {
      try {
        resolve(block());
      } catch (error) {
        reject(error);
      }
    });
  });
}
var PROFILE_CONFIG_SKIP = /* @__PURE__ */ new Set([
  "boardControl",
  "slotControl",
  "specialAbilities",
  "specialPieces",
  "boardAbilities",
  "entryTicket",
  "mutationLab"
]);
var PROFILE_REFERENCE_ONLY = /* @__PURE__ */ new Set([
  "Match3Engine.GameLogic",
  "Match3Engine.PlayerControl",
  "Match3Engine.PlayerModel"
]);
var PROFILE_PRIMITIVES = {
  "System.Int32": (h) => h.readS32(),
  "System.UInt32": (h) => h.readU32(),
  "System.Int16": (h) => h.readS16(),
  "System.UInt16": (h) => h.readU16(),
  "System.Byte": (h) => h.readU8(),
  "System.SByte": (h) => h.readS8(),
  "System.Boolean": (h) => h.readU8() !== 0,
  "System.Single": (h) => h.readFloat(),
  "System.Double": (h) => h.readDouble(),
  "System.Int64": (h) => Number(h.readS64()),
  "System.UInt64": (h) => Number(h.readU64())
};
function profileReader(budget = 5e4) {
  let remaining = budget;
  const issues = [];
  const active = /* @__PURE__ */ new Set();
  function problem(path, reason) {
    issues.push({ path, reason });
    return { unresolved: reason };
  }
  function value(raw, path, depth = 0) {
    if (--remaining < 0) return problem(path, "node budget");
    if (raw == null || typeof raw === "number" || typeof raw === "boolean" || typeof raw === "string") return raw;
    if (depth > 32) return problem(path, "depth budget");
    if (raw instanceof Int64 || raw instanceof UInt64) return raw.toNumber();
    if (raw.handle != null && raw.handle.isNull()) return null;
    if (raw instanceof Il2Cpp.String) return raw.content;
    if (raw instanceof Il2Cpp.Array) raw = raw.object;
    const klass = raw instanceof Il2Cpp.ValueType ? raw.type.class : raw.class;
    if (klass == null) return problem(path, "unknown runtime value");
    const type = String(klass.type.name);
    if (klass.isEnum) return value(raw.field("value__").value, path, depth + 1);
    const primitive = PROFILE_PRIMITIVES[type];
    if (primitive != null && !(raw instanceof Il2Cpp.ValueType)) return primitive(raw.handle.add(16));
    if (type === "System.String") return asText(raw);
    const identity = type + ":" + raw.handle;
    if (active.has(identity)) return { reference_type: type };
    active.add(identity);
    try {
      if (type.endsWith("[]") || type.includes("[,]")) {
        const array = new Il2Cpp.Array(raw.handle);
        if (array.length > 4096) return problem(path, "array length " + array.length);
        const out = [];
        for (let i = 0; i < array.length; i++) out.push(value(array.get(i), path + "[" + i + "]", depth + 1));
        return out;
      }
      if (type.startsWith("System.Collections.Generic.List<")) {
        const size = Number(fieldValue(raw, "_size"));
        if (!Number.isInteger(size) || size < 0 || size > 4096) return problem(path, "invalid list size");
        return listItemsByField(raw, 4096).map((item, i) => value(item, path + "[" + i + "]", depth + 1));
      }
      if (type.startsWith("System.Collections.Generic.Dictionary<")) {
        let count = Number(fieldValue(raw, "_count"));
        if (!Number.isFinite(count)) count = Number(fieldValue(raw, "count"));
        if (!Number.isInteger(count) || count < 0 || count > 4096) return problem(path, "invalid dictionary count");
        if (count === 0) return { entries: [] };
        const entries = fieldValue(raw, "_entries") ?? fieldValue(raw, "entries");
        if (entries == null) return problem(path, "dictionary entries missing");
        const array = new Il2Cpp.Array(entries.handle);
        if (count > array.length) return problem(path, "dictionary count exceeds capacity");
        const out = [];
        for (let i = 0; i < count; i++) {
          const entry = array.get(i);
          if (Number(fieldValue(entry, "hashCode") ?? 0) < 0) continue;
          if (Number(fieldValue(entry, "next") ?? 0) < -1) continue;
          out.push({
            key: value(entry.field("key").value, path + ".key" + i, depth + 1),
            value: value(entry.field("value").value, path + ".value" + i, depth + 1)
          });
        }
        return { entries: out };
      }
      if (type.startsWith("System.Collections.Generic.HashSet<")) {
        const count = Number(fieldValue(raw, "_count") ?? fieldValue(raw, "count"));
        if (!Number.isInteger(count) || count < 0 || count > 4096) return problem(path, "invalid set count");
        if (count === 0) return { items: [] };
        const slots = fieldValue(raw, "_slots") ?? fieldValue(raw, "_entries") ?? fieldValue(raw, "entries");
        if (slots == null) return problem(path, "set slots missing");
        const array = new Il2Cpp.Array(slots.handle);
        const last = Number(fieldValue(raw, "_lastIndex") ?? count);
        if (!Number.isInteger(last) || last < 0 || last > array.length) return problem(path, "set index exceeds capacity");
        const out = [];
        for (let i = 0; i < last; i++) {
          const slot = array.get(i);
          if (Number(fieldValue(slot, "hashCode") ?? 0) < 0) continue;
          if (Number(fieldValue(slot, "next") ?? 0) < -1) continue;
          out.push(value(slot.field("value").value, path + "[" + i + "]", depth + 1));
        }
        return { items: out };
      }
      if (!type.startsWith("Match3Engine.") && !type.startsWith("System.Nullable<") && !type.startsWith("FixMath.") && !type.startsWith("FroggyFuLotusPlacementPlanner")) {
        return problem(path, "unsupported type " + type);
      }
      if (PROFILE_REFERENCE_ONLY.has(type)) return { reference_type: type };
      return fields(raw, path, depth + 1);
    } catch (error) {
      return problem(path, String(error));
    } finally {
      active.delete(identity);
    }
  }
  function fields(object, path, depth = 0, skip) {
    const out = {};
    let klass = object instanceof Il2Cpp.ValueType ? object.type.class : object.class;
    while (klass != null && klass.type.name !== "System.Object" && klass.type.name !== "System.ValueType") {
      for (const f of klass.fields) {
        if (f.isStatic || f.isLiteral || skip != null && skip.has(f.name)) continue;
        const typeName = String(f.type.name);
        if (typeName.startsWith("System.Action") || typeName.startsWith("System.Func") || typeName.includes("Callback")) continue;
        try {
          out[f.name] = value(object.field(f.name).value, path + "." + f.name, depth + 1);
        } catch (error) {
          out[f.name] = problem(path + "." + f.name, String(error));
        }
      }
      klass = klass.parent;
    }
    return out;
  }
  return { value, fields, issues };
}
var cachedProfileKey = null;
var cachedProfileStatic = null;
var mixyTraceArmed = false;
var boosterDetailArmed = false;
var mixyTraceListeners = [];
var mixyTraceError = null;
var mixyTraceAbility = null;
var mixyTraceLogic = null;
var mixyTracePending = null;
var mixyTraceHistory = [];
var mixyRefillHistory = [];
var jellyTraceListeners = [];
var jellyTraceError = null;
var jellyTraceAbility = null;
var jellyTraceActive = null;
var jellyTraceHistory = [];
function mixyTraceCounter(logic) {
  return ruleFieldValue(fieldValue(logic, "<Random>k__BackingField"), "<counter>k__BackingField");
}
function refillTraceGrid(board) {
  const rows = asNumber(fieldValue(board, "<Rows>k__BackingField"));
  const columns = asNumber(fieldValue(board, "<Columns>k__BackingField"));
  if (rows < 4 || rows > 12 || columns < 4 || columns > 12) throw new Error("invalid Mixy trace board");
  const slots = board.handle.add(EXPECTED_OFFSETS["BoardModel.slots"]).readPointer();
  const cells = slots.add(Il2Cpp.Array.headerSize);
  return Array.from({ length: rows }, (_, y) => Array.from({ length: columns }, (_2, x) => {
    const pointer = cells.add((x * rows + y) * Process.pointerSize).readPointer();
    if (pointer.isNull()) return null;
    const slot = new Il2Cpp.Object(pointer);
    return [
      asNumber(readSlotField(slot, "color")),
      asNumber(readSlotField(slot, "value")),
      readBoolean(slot, "canBeMatched")
    ];
  }));
}
function mixyTraceFrame(logic, ability, board) {
  const rng = fieldValue(logic, "<Random>k__BackingField");
  return {
    rng_counter: ruleFieldValue(rng, "<counter>k__BackingField"),
    rng_index: ruleFieldValue(rng, "_index"),
    active_colors: intListValues(fieldValue(ability, "activeColors")),
    target_color: ruleFieldValue(ability, "TargetColor"),
    moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
    grid: refillTraceGrid(board)
  };
}
var swapTraceListeners = [];
var swapTraceError = null;
var swapTraceActive = null;
var swapTraceInSwap = null;
var swapTraceCleoDepth = 0;
var swapTraceHistory = [];
var SWAP_TRACE_EVENT_LIMIT = 400;
function tracePoint(raw) {
  const value = uint64(raw.toString());
  return [value.and(4294967295).toNumber() | 0, value.shr(32).and(4294967295).toNumber() | 0];
}
function swapTraceGrid(board) {
  const rows = asNumber(fieldValue(board, "<Rows>k__BackingField"));
  const columns = asNumber(fieldValue(board, "<Columns>k__BackingField"));
  if (rows < 4 || rows > 12 || columns < 4 || columns > 12) throw new Error("invalid swap trace board");
  const slots = board.handle.add(EXPECTED_OFFSETS["BoardModel.slots"]).readPointer();
  const cells = slots.add(Il2Cpp.Array.headerSize);
  return Array.from({ length: rows }, (_, y) => Array.from({ length: columns }, (_2, x) => {
    const pointer = cells.add((x * rows + y) * Process.pointerSize).readPointer();
    if (pointer.isNull()) return null;
    const slot = new Il2Cpp.Object(pointer);
    return [
      asNumber(readSlotField(slot, "color")),
      asNumber(readSlotField(slot, "color2")),
      asNumber(readSlotField(slot, "value"))
    ];
  }));
}
function swapTraceEvent(type, fields) {
  const trace = swapTraceActive;
  if (trace == null) return;
  if (trace.events.length >= SWAP_TRACE_EVENT_LIMIT) {
    trace.truncated = true;
    return;
  }
  trace.events.push({ type, ...fields });
}
function swapTraceCounter() {
  const trace = swapTraceActive;
  return trace == null ? null : mixyTraceCounter(trace.logic);
}
function liveBoard(board) {
  const trace = swapTraceActive;
  return trace != null && trace.board.handle.equals(board);
}
function slotSummary(raw) {
  if (raw.isNull()) return null;
  const slot = new Il2Cpp.Object(raw);
  return {
    color: asNumber(readSlotField(slot, "color")),
    color2: asNumber(readSlotField(slot, "color2")),
    value: asNumber(readSlotField(slot, "value"))
  };
}
function installSwapTrace() {
  if (swapTraceListeners.length || swapTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const analyzer = image.class("Match3Engine.BoardAnalyzer");
    const address = (klass, name, count) => {
      const pointer = klass.method(name, count).virtualAddress;
      if (pointer.isNull()) throw new Error("swap trace: " + name + " address missing");
      return pointer;
    };
    const swap = address(image.class("Match3Engine.GameLogic"), "ValidSwapPerformed", 5);
    const merge = address(analyzer, "GetMergeSwapOutcome", 4);
    const area = address(analyzer, "GetAreaOfEffectByPiece", 5);
    const destroy = address(analyzer, "GetAreaOfEffectDestructionSlots", 5);
    const fireworks = address(image.class("Match3Engine.BoardModel"), "GetFireworks", 4);
    listeners.push(Interceptor.attach(swap, {
      onEnter(args) {
        if (!boosterDetailArmed || cachedGameLogic == null || !cachedGameLogic.handle.equals(args[0])) return;
        try {
          const logic = new Il2Cpp.Object(args[0]);
          const board = boardObject(logic);
          swapTraceActive = {
            logic,
            board,
            logic_key: String(args[0]),
            events: [],
            position1: tracePoint(args[1]),
            position2: tracePoint(args[2]),
            is_player_move: (args[3].toInt32() & 1) === 1,
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            grid: swapTraceGrid(board)
          };
          swapTraceHistory.push(swapTraceActive);
          if (swapTraceHistory.length > 4) swapTraceHistory.shift();
          swapTraceInSwap = this.threadId;
          this.swapTraceOpen = true;
        } catch (error) {
          swapTraceError = String(error);
        }
      },
      onLeave() {
        if (this.swapTraceOpen) swapTraceInSwap = null;
      }
    }));
    listeners.push(Interceptor.attach(merge, {
      onEnter(args) {
        if (!liveBoard(args[0]) || swapTraceInSwap !== this.threadId) return;
        this.swapMerge = {
          source: tracePoint(args[1]),
          target: tracePoint(args[2]),
          is_after_swap: (args[3].toInt32() & 1) === 1,
          rng: swapTraceCounter()
        };
      },
      onLeave(result) {
        const call = this.swapMerge;
        if (call == null) return;
        try {
          call.outcome = result.isNull() ? null : profileReader(2e3).fields(new Il2Cpp.Object(result), "swap_trace.merge");
          swapTraceEvent("merge_outcome", call);
        } catch (error) {
          swapTraceEvent("merge_outcome", { ...call, unresolved: String(error) });
        }
      }
    }));
    listeners.push(Interceptor.attach(area, {
      onEnter(args) {
        if (!liveBoard(args[1])) return;
        try {
          this.swapArea = {
            piece: slotSummary(args[2]),
            position: tracePoint(args[3]),
            rng_before: swapTraceCounter()
          };
        } catch (error) {
          this.swapArea = { unresolved: String(error) };
        }
      },
      onLeave(result) {
        const call = this.swapArea;
        if (call == null) return;
        try {
          call.cells = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 128);
          call.rng_after = swapTraceCounter();
        } catch (error) {
          call.unresolved = String(error);
        }
        swapTraceEvent("piece_area", call);
      }
    }));
    listeners.push(Interceptor.attach(destroy, {
      onEnter(args) {
        if (!liveBoard(args[0])) return;
        try {
          this.swapDestroy = {
            positions: args[1].isNull() ? null : pointListValues(new Il2Cpp.Object(args[1]), 128),
            rng_before: swapTraceCounter()
          };
        } catch (error) {
          this.swapDestroy = { unresolved: String(error) };
        }
        try {
          const trace = swapTraceActive;
          if (trace != null) this.swapDestroy.grid = swapTraceGrid(trace.board);
        } catch (error) {
          this.swapDestroy.grid_error = String(error);
        }
      },
      onLeave() {
        const call = this.swapDestroy;
        if (call == null) return;
        call.rng_after = swapTraceCounter();
        swapTraceEvent("destroy_pass", call);
      }
    }));
    listeners.push(Interceptor.attach(fireworks, {
      onEnter(args) {
        if (!liveBoard(args[0])) return;
        try {
          this.swapFireworks = {
            amount: args[1].toInt32(),
            position: tracePoint(args[2]),
            ignore: args[3].isNull() ? null : pointListValues(new Il2Cpp.Object(args[3]), 128),
            rng_before: swapTraceCounter()
          };
        } catch (error) {
          this.swapFireworks = { unresolved: String(error) };
        }
      },
      onLeave(result) {
        const call = this.swapFireworks;
        if (call == null) return;
        try {
          call.picks = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 128);
          call.rng_after = swapTraceCounter();
        } catch (error) {
          call.unresolved = String(error);
        }
        swapTraceEvent("fireworks", call);
      }
    }));
    swapTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    swapTraceError = String(error);
  }
}
var cleoTraceListeners = [];
var cleoTraceError = null;
function removeCleoTrace() {
  for (const listener of cleoTraceListeners) {
    try {
      listener.detach();
    } catch (_error) {
    }
  }
  cleoTraceListeners = [];
  swapTraceCleoDepth = 0;
}
function installCleoTrace() {
  if (cleoTraceListeners.length || cleoTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const address = (klass, name, count) => {
      const pointer = klass.method(name, count).virtualAddress;
      if (pointer.isNull()) throw new Error("cleo trace: " + name + " address missing");
      return pointer;
    };
    const cleoLogic = image.class("Match3Engine.CleoCadabraPieceLogic");
    const cleoSwap = address(cleoLogic, "SwapPerformed", 3);
    const cleoConvert = address(cleoLogic, "ConvertToPiece", 1);
    const allCombos = address(image.class("Match3Engine.BoardAnalyzer"), "GetAllCombos", 4);
    const chance = address(image.class("Match3Engine.RandomWrapper"), "Chance", 1);
    listeners.push(Interceptor.attach(cleoSwap, {
      onEnter(args) {
        if (swapTraceActive == null) return;
        swapTraceCleoDepth += 1;
        this.swapCleo = true;
        swapTraceEvent("cleo_swap_begin", {
          position1: tracePoint(args[1]),
          position2: tracePoint(args[2]),
          rng: swapTraceCounter()
        });
      },
      onLeave() {
        if (!this.swapCleo) return;
        swapTraceCleoDepth -= 1;
        swapTraceEvent("cleo_swap_end", { rng: swapTraceCounter() });
      }
    }));
    listeners.push(Interceptor.attach(cleoConvert, {
      onEnter(args) {
        if (swapTraceActive == null) return;
        this.swapConvert = {
          position: tracePoint(args[1]),
          rng: swapTraceCounter(),
          inside_swap: swapTraceCleoDepth > 0
        };
      },
      onLeave() {
        if (this.swapConvert != null) swapTraceEvent("cleo_convert", this.swapConvert);
      }
    }));
    listeners.push(Interceptor.attach(allCombos, {
      onEnter(args) {
        if (swapTraceActive == null || swapTraceCleoDepth <= 0) return;
        try {
          this.swapCombos = {
            test_slots: args[1].isNull() ? null : pointListValues(new Il2Cpp.Object(args[1]), 128),
            rng: swapTraceCounter()
          };
        } catch (error) {
          this.swapCombos = { unresolved: String(error) };
        }
      },
      onLeave(result) {
        const call = this.swapCombos;
        if (call == null) return;
        try {
          call.combos = result.isNull() ? null : profileReader(4e3).value(new Il2Cpp.Object(result), "swap_trace.cleo_combos");
        } catch (error) {
          call.unresolved = String(error);
        }
        swapTraceEvent("cleo_all_combos", call);
      }
    }));
    listeners.push(Interceptor.attach(chance, {
      onEnter(args) {
        if (swapTraceActive == null || swapTraceCleoDepth <= 0) return;
        this.swapChance = { percent: args[1].toInt32(), rng: swapTraceCounter() };
      },
      onLeave(result) {
        if (this.swapChance == null) return;
        this.swapChance.result = (result.toInt32() & 1) === 1;
        swapTraceEvent("cleo_chance", this.swapChance);
      }
    }));
    cleoTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    cleoTraceError = String(error);
  }
}
var woollyTraceListeners = [];
var woollyTraceError = null;
function removeWoollyTrace() {
  for (const listener of woollyTraceListeners) {
    try {
      listener.detach();
    } catch (_error) {
    }
  }
  woollyTraceListeners = [];
}
function installWoollyTrace() {
  if (woollyTraceListeners.length || woollyTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const address = (klass, name, count) => {
      const pointer = klass.method(name, count).virtualAddress;
      if (pointer.isNull()) throw new Error("woolly trace: " + name + " address missing");
      return pointer;
    };
    const use = address(image.class("Match3Engine.WoollyWorkout"), "Use", 1);
    const convert = address(image.class("Match3Engine.GameLogic"), "ConvertSlots", 1);
    listeners.push(Interceptor.attach(use, {
      onEnter(args) {
        if (!boosterDetailArmed || cachedGameLogic == null || !cachedGameLogic.handle.equals(args[1])) return;
        try {
          const logic = new Il2Cpp.Object(args[1]);
          const board = boardObject(logic);
          swapTraceActive = {
            kind: "woolly",
            logic,
            board,
            logic_key: String(args[1]),
            events: [],
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            grid: swapTraceGrid(board)
          };
          swapTraceHistory.push(swapTraceActive);
          if (swapTraceHistory.length > 4) swapTraceHistory.shift();
          this.woollyAbility = args[0];
          this.woollyTrace = swapTraceActive;
        } catch (error) {
          woollyTraceError = String(error);
        }
      },
      onLeave() {
        const trace = this.woollyTrace;
        if (trace == null) return;
        trace.use_rng_after = mixyTraceCounter(trace.logic);
        try {
          const ability = new Il2Cpp.Object(this.woollyAbility);
          const skip = /* @__PURE__ */ new Set(["player"]);
          for (const field of ability.class.fields) {
            if (String(field.name).startsWith("anim")) skip.add(String(field.name));
          }
          trace.ability = profileReader(3e3).fields(ability, "woolly_trace.ability", 0, skip);
        } catch (error) {
          trace.ability_unresolved = String(error);
        }
      }
    }));
    listeners.push(Interceptor.attach(convert, {
      onEnter(args) {
        const trace = swapTraceActive;
        if (trace == null || trace.kind !== "woolly" || !trace.logic.handle.equals(args[0])) return;
        this.woollyConvert = { rng_before: swapTraceCounter() };
        try {
          this.woollyConvert.model = profileReader(3e3).fields(
            new Il2Cpp.Object(args[1]),
            "woolly_trace.conversion"
          );
        } catch (error) {
          this.woollyConvert.model_unresolved = String(error);
        }
      },
      onLeave() {
        const call = this.woollyConvert;
        const trace = swapTraceActive;
        if (call == null || trace == null) return;
        call.rng_after = swapTraceCounter();
        try {
          call.grid_after = swapTraceGrid(trace.board);
        } catch (error) {
          call.grid_unresolved = String(error);
        }
        swapTraceEvent("woolly_convert", call);
      }
    }));
    woollyTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    woollyTraceError = String(error);
  }
}
var boosterTraceListeners = [];
var boosterTraceError = null;
var boosterTraceClass = null;
function removeBoosterTrace() {
  for (const listener of boosterTraceListeners) {
    try {
      listener.detach();
    } catch (_error) {
    }
  }
  boosterTraceListeners = [];
  boosterTraceClass = null;
}
function installBoosterTrace(ability) {
  const name = String(ability.class.type.name);
  if (boosterTraceClass === name || boosterTraceError != null) return;
  removeBoosterTrace();
  try {
    const use = ability.class.method("Use", 1).virtualAddress;
    if (use.isNull()) throw new Error("booster trace: Use address missing");
    boosterTraceListeners.push(Interceptor.attach(use, {
      onEnter(args) {
        if (!boosterDetailArmed || cachedGameLogic == null || !cachedGameLogic.handle.equals(args[1])) return;
        try {
          const logic = new Il2Cpp.Object(args[1]);
          const board = boardObject(logic);
          swapTraceActive = {
            kind: "booster",
            ability: name,
            logic,
            board,
            logic_key: String(args[1]),
            events: [],
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            grid: swapTraceGrid(board)
          };
          swapTraceHistory.push(swapTraceActive);
          if (swapTraceHistory.length > 4) swapTraceHistory.shift();
          this.boosterTrace = swapTraceActive;
        } catch (error) {
          boosterTraceError = String(error);
        }
      },
      onLeave() {
        const trace = this.boosterTrace;
        if (trace != null) trace.use_rng_after = mixyTraceCounter(trace.logic);
      }
    }));
    boosterTraceClass = name;
  } catch (error) {
    boosterTraceError = String(error);
  }
}
var charlesTraceListeners = [];
var charlesTraceError = null;
function removeCharlesTrace() {
  for (const listener of charlesTraceListeners) {
    try {
      listener.detach();
    } catch (_error) {
    }
  }
  charlesTraceListeners = [];
}
function installCharlesTrace() {
  if (charlesTraceListeners.length || charlesTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const charles = image.class("Match3Engine.CheckmateCharles");
    const address = (klass, name, count) => {
      const pointer = klass.method(name, count).virtualAddress;
      if (pointer.isNull()) throw new Error("charles trace: " + name + " address missing");
      return pointer;
    };
    const use = address(charles, "Use", 1);
    const explosion = address(charles, "ChoosePositionsForActivateExplosion", 1);
    const refill = address(charles, "RefillExplodedSpecials", 2);
    const knights = address(charles, "ChoosePositionsForKnights", 2);
    listeners.push(Interceptor.attach(use, {
      onEnter(args) {
        if (!boosterDetailArmed || cachedGameLogic == null || !cachedGameLogic.handle.equals(args[1])) return;
        try {
          const logic = new Il2Cpp.Object(args[1]);
          const board = boardObject(logic);
          swapTraceActive = {
            kind: "charles",
            logic,
            board,
            logic_key: String(args[1]),
            events: [],
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            grid: swapTraceGrid(board)
          };
          swapTraceHistory.push(swapTraceActive);
          if (swapTraceHistory.length > 4) swapTraceHistory.shift();
          this.charlesTrace = swapTraceActive;
        } catch (error) {
          charlesTraceError = String(error);
        }
      },
      onLeave() {
        const trace = this.charlesTrace;
        if (trace != null) trace.use_rng_after = mixyTraceCounter(trace.logic);
      }
    }));
    listeners.push(Interceptor.attach(explosion, {
      onEnter() {
        const trace = swapTraceActive;
        if (trace == null || trace.kind !== "charles") return;
        this.charlesExplosion = { rng_before: swapTraceCounter() };
      },
      onLeave(result) {
        const call = this.charlesExplosion;
        if (call == null) return;
        try {
          call.cells = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 128);
        } catch (error) {
          call.unresolved = String(error);
        }
        call.rng_after = swapTraceCounter();
        swapTraceEvent("charles_explosion", call);
      }
    }));
    listeners.push(Interceptor.attach(refill, {
      onEnter(args) {
        const trace = swapTraceActive;
        if (trace == null || trace.kind !== "charles" || !trace.logic.handle.equals(args[1])) return;
        this.charlesRefill = { rng_before: swapTraceCounter() };
        try {
          this.charlesRefill.grid_before = swapTraceGrid(trace.board);
        } catch (error) {
          this.charlesRefill.grid_unresolved = String(error);
        }
      },
      onLeave() {
        const call = this.charlesRefill;
        const trace = swapTraceActive;
        if (call == null || trace == null) return;
        call.rng_after = swapTraceCounter();
        try {
          call.grid_after = swapTraceGrid(trace.board);
        } catch (error) {
          call.grid_unresolved = String(error);
        }
        swapTraceEvent("charles_refill", call);
      }
    }));
    listeners.push(Interceptor.attach(knights, {
      onEnter(args) {
        const trace = swapTraceActive;
        if (trace == null || trace.kind !== "charles") return;
        this.charlesKnights = { count: args[2].toInt32(), rng_before: swapTraceCounter() };
      },
      onLeave(result) {
        const call = this.charlesKnights;
        if (call == null) return;
        try {
          call.cells = result.isNull() ? null : pointListValues(new Il2Cpp.Object(result), 64);
        } catch (error) {
          call.unresolved = String(error);
        }
        call.rng_after = swapTraceCounter();
        swapTraceEvent("charles_knights", call);
      }
    }));
    charlesTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    charlesTraceError = String(error);
  }
}
function installJellyTrace() {
  if (jellyTraceListeners.length || jellyTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const fresh = image.class("Match3Engine.JellySE").method("SetFreshJellies", 2).virtualAddress;
    const search = image.class("Match3Engine.JellySEPointsFinder").nested("ImprovedFinder").method("ImprovedSearch", 5).virtualAddress;
    if (fresh.isNull() || search.isNull()) throw new Error("Jelly trace method address missing");
    listeners.push(Interceptor.attach(fresh, {
      onEnter(args) {
        if (args[2].toInt32() !== 0 || !jellyTraceAbility?.equals(args[0]) || !cachedGameLogic?.handle.equals(args[1])) return;
        const logic = new Il2Cpp.Object(args[1]);
        try {
          const trace = {
            logic_key: String(args[1]),
            thread_id: this.threadId,
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            grid: refillTraceGrid(boardObject(logic))
          };
          jellyTraceActive = trace;
          this.jellyTrace = { logic, trace };
        } catch (error) {
          jellyTraceError = String(error);
        }
      },
      onLeave() {
        const current = this.jellyTrace;
        if (current == null) return;
        jellyTraceActive = null;
        try {
          current.trace.after_rng_counter = mixyTraceCounter(current.logic);
          jellyTraceHistory.push(current.trace);
          if (jellyTraceHistory.length > 8) jellyTraceHistory.shift();
        } catch (error) {
          jellyTraceError = String(error);
        }
      }
    }));
    listeners.push(Interceptor.attach(search, {
      onEnter(args) {
        const trace = jellyTraceActive;
        if (trace == null || trace.thread_id !== this.threadId || trace.logic_key !== String(args[2])) return;
        try {
          const logic = new Il2Cpp.Object(args[2]);
          trace.search_rng_counter = mixyTraceCounter(logic);
          trace.search_config = readAllInstanceFields(new Il2Cpp.Object(args[5]));
          this.jellySearchTrace = trace;
        } catch (error) {
          jellyTraceError = String(error);
        }
      },
      onLeave(result) {
        const trace = this.jellySearchTrace;
        if (trace == null || result.isNull()) return;
        try {
          const tuple = new Il2Cpp.Object(result);
          trace.selected_points = pointListValues(
            fieldValue(tuple, "m_Item1") ?? fieldValue(tuple, "Item1")
          );
        } catch (error) {
          jellyTraceError = String(error);
        }
      }
    }));
    jellyTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    jellyTraceError = String(error);
  }
}
function installMixyTrace() {
  if (mixyTraceListeners.length || mixyTraceError != null) return;
  const listeners = [];
  try {
    const image = findAssemblyImage();
    const redeal = image.class("Match3Engine.MixyMeow").method("RandomizeActiveColors", 1).virtualAddress;
    const refill = image.class("Match3Engine.SpawningEngine").method("FillAllEmptySlots", 5).virtualAddress;
    if (redeal.isNull() || refill.isNull()) throw new Error("Mixy trace method address missing");
    listeners.push(Interceptor.attach(redeal, {
      onEnter(args) {
        if (!mixyTraceArmed || !mixyTraceAbility?.equals(args[0]) || !mixyTraceLogic?.equals(args[1])) return;
        mixyTracePending = null;
        try {
          const logic = new Il2Cpp.Object(args[1]);
          const ability = new Il2Cpp.Object(args[0]);
          this.mixyTrace = {
            logic,
            ability,
            record: {
              logic_key: String(args[1]),
              before_redeal: mixyTraceFrame(logic, ability, boardObject(logic)),
              preceding_refills: mixyRefillHistory.filter(
                (refill2) => refill2.logic_key === String(args[1])
              ).slice(-8)
            }
          };
        } catch (error) {
          mixyTraceError = String(error);
        }
      },
      onLeave() {
        const trace = this.mixyTrace;
        if (trace == null) return;
        try {
          trace.record.after_redeal = mixyTraceFrame(trace.logic, trace.ability, boardObject(trace.logic));
          mixyTraceHistory.push(trace.record);
          if (mixyTraceHistory.length > 8) mixyTraceHistory.shift();
          mixyTracePending = trace.record;
        } catch (error) {
          mixyTraceError = String(error);
        }
      }
    }));
    listeners.push(Interceptor.attach(refill, {
      onEnter(args) {
        if (!mixyTraceLogic?.equals(args[1]) || mixyTraceAbility == null) return;
        try {
          const logic = new Il2Cpp.Object(args[1]);
          const board = boardObject(logic);
          if (!board.handle.equals(args[2])) return;
          this.mixyRefill = { logic, frame: {
            logic_key: String(args[1]),
            before_rng_counter: mixyTraceCounter(logic),
            moves_made: ruleFieldValue(logic, "<MovesMadeThisTurn>k__BackingField"),
            chain_reaction: Boolean(args[4].toInt32())
          } };
          const trace = mixyTracePending;
          if (trace != null) {
            mixyTracePending = null;
            trace.before_refill = mixyTraceFrame(logic, new Il2Cpp.Object(mixyTraceAbility), board);
          }
        } catch (error) {
          mixyTraceError = String(error);
        }
      },
      onLeave() {
        const refill2 = this.mixyRefill;
        if (refill2 == null) return;
        try {
          refill2.frame.after_rng_counter = mixyTraceCounter(refill2.logic);
          mixyRefillHistory.push(refill2.frame);
          if (mixyRefillHistory.length > 16) mixyRefillHistory.shift();
        } catch (error) {
          mixyTraceError = String(error);
        }
      }
    }));
    mixyTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    mixyTraceError = String(error);
  }
}
function readCleoPieceLogic(logic, reader) {
  const all = readPieceLogics(logic, reader, 32);
  if (all == null || !Array.isArray(all)) return all;
  return all.length === 0 ? null : all[0].fields;
}
function readPieceLogics(logic, reader, onlyKey) {
  try {
    const dictionary = fieldValue(logic, "specialPiecesLogics");
    if (dictionary == null) return null;
    const count = Number(fieldValue(dictionary, "_count") ?? fieldValue(dictionary, "count"));
    if (!Number.isInteger(count) || count < 0 || count > 4096) {
      return { unresolved: "invalid specialPiecesLogics count" };
    }
    if (count === 0) return [];
    const entries = fieldValue(dictionary, "_entries") ?? fieldValue(dictionary, "entries");
    if (entries == null) return { unresolved: "specialPiecesLogics entries missing" };
    const array = new Il2Cpp.Array(entries.handle);
    if (count > array.length) return { unresolved: "specialPiecesLogics count exceeds capacity" };
    const out = [];
    for (let i = 0; i < count; i++) {
      const entry = array.get(i);
      if (Number(fieldValue(entry, "hashCode") ?? 0) < 0 || Number(fieldValue(entry, "next") ?? 0) < -1) continue;
      const key = ruleFieldValue(entry, "key");
      if (onlyKey != null && key !== onlyKey) continue;
      const piece = fieldValue(entry, "value");
      if (piece == null) continue;
      const path = onlyKey === 32 ? "cleo_piece_logic" : "special_pieces_logics." + key;
      out.push({ key, class: String(piece.class.type.name), fields: reader.fields(piece, path) });
      if (onlyKey != null) break;
    }
    return out;
  } catch (error) {
    return { unresolved: String(error) };
  }
}
function readMatchProfile(withStatic) {
  if (!matchActive) throw new Error("no active match");
  const logic = resolveGameLogic();
  const key = String(logic.handle);
  const reader = profileReader();
  const rng = fieldValue(logic, "<Random>k__BackingField");
  const counterBefore = fieldValue(rng, "<counter>k__BackingField");
  const result = {
    schema_version: 1,
    logic_key: key,
    rules_id: asText(fieldValue(fieldValue(logic, "gameRules"), "id")),
    rng: rng == null ? null : reader.fields(rng, "rng"),
    spawning: reader.value(fieldValue(logic, "spawningEngine"), "spawning"),
    // Dynamic reads: PieceUsesThisTurn 0x5ae429c reads board.extraData;
    // the loaded Cleo config/overrides can change during a match.
    cleo_piece_logic: readCleoPieceLogic(logic, reader),
    board_extra_data: reader.value(fieldValue(fieldValue(logic, "board"), "extraData"), "board_extra_data"),
    cleo_booster_fields: (() => {
      const local = listItemsByField(fieldValue(logic, "players")).find(
        (control) => ruleFieldValue(control, "<Type>k__BackingField") === 0
      );
      const ability = fieldValue(local, "ability");
      return ability != null && String(ability.class.type.name) === "Match3Engine.CleoCadabra" ? reader.fields(ability, "cleo_booster_fields") : null;
    })(),
    // Configuration and this activation's rolls (rolledPreferredColorThisActivation,
    // plannedLotusPositionsThisActivation, cachedSwapResolution). Field reads only;
    // animation timings, the planner object and the player reference add nothing.
    froggy_booster_fields: (() => {
      const local = listItemsByField(fieldValue(logic, "players")).find(
        (control) => ruleFieldValue(control, "<Type>k__BackingField") === 0
      );
      const ability = fieldValue(local, "ability");
      if (ability == null || String(ability.class.type.name) !== "Match3Engine.FroggyFu") return null;
      const skip = /* @__PURE__ */ new Set(["_froggyFuAttractionPlanner", "player"]);
      for (const field of ability.class.fields) {
        if (String(field.name).startsWith("anim")) skip.add(String(field.name));
      }
      return reader.fields(ability, "froggy_booster_fields", 0, skip);
    })(),
    // SpecialAbility.get_ActivatesThisTurn 0x5ad91c8: a plain Int32 on
    // PlayerModel, not an ability method invocation or a remaining-use estimate.
    cleo_activates_this_turn: (() => {
      const local = listItemsByField(fieldValue(logic, "players")).find(
        (control) => ruleFieldValue(control, "<Type>k__BackingField") === 0
      );
      const model = fieldValue(local, "model");
      return model == null ? null : ruleFieldValue(model, "specialAbilityUsedThisTurn");
    })(),
    state: reader.fields(logic, "state", 0, new Set(
      logic.class.fields.map((f) => String(f.name)).filter((name) => ![
        "moves",
        "currentPlayerIndex",
        "currentGameState",
        "<GameIndex>k__BackingField",
        "<ChainReaction>k__BackingField",
        "<Turns>k__BackingField",
        "<TurnsTotal>k__BackingField",
        "<MovesMadeThisTurn>k__BackingField"
      ].includes(name))
    )),
    // Game numbers only, the same allow-list as the capture agent: the
    // account's ids and name live on PlayerModel too and are never read.
    players: listItemsByField(fieldValue(logic, "players")).map((control, i) => {
      const model = fieldValue(control, "model");
      return {
        player_type: ruleFieldValue(control, "<Type>k__BackingField"),
        model: model == null ? null : reader.fields(model, "players." + i, 0, new Set(
          model.class.fields.map((f) => String(f.name)).filter((name) => ![
            "index",
            "score",
            "spawnBonus",
            "slotType",
            "energy",
            "boardAbilities",
            "specialAbilityType",
            "scoreMultiplier",
            "soloScoreTargetInd"
          ].includes(name))
        ))
      };
    })
  };
  if (mixyTraceArmed) {
    const local = listItemsByField(fieldValue(logic, "players")).find(
      (control) => ruleFieldValue(control, "<Type>k__BackingField") === 0
    );
    const ability = fieldValue(local, "ability");
    mixyTraceLogic = logic.handle;
    mixyTraceAbility = ability != null && String(ability.class.type.name) === "Match3Engine.MixyMeow" ? ability.handle : null;
    if (mixyTraceAbility != null) installMixyTrace();
    jellyTraceAbility = ability != null && String(ability.class.type.name) === "Match3Engine.JellySE" ? ability.handle : null;
    if (jellyTraceAbility != null) installJellyTrace();
    result.mixy_redeal_trace = mixyTraceHistory.filter((trace) => trace.logic_key === key);
    if (mixyTraceError != null) result.mixy_redeal_trace_error = mixyTraceError;
    result.jelly_renewal_trace = jellyTraceHistory.filter((trace) => trace.logic_key === key);
    if (jellyTraceError != null) result.jelly_renewal_trace_error = jellyTraceError;
  }
  if (boosterDetailArmed) {
    const detail = profileReader();
    const local = listItemsByField(fieldValue(logic, "players")).find(
      (control) => ruleFieldValue(control, "<Type>k__BackingField") === 0
    );
    const ability = fieldValue(local, "ability");
    let abilityDetail = null;
    if (ability != null) {
      const skip = /* @__PURE__ */ new Set(["player"]);
      for (const field of ability.class.fields) {
        if (String(field.name).startsWith("anim")) skip.add(String(field.name));
      }
      try {
        abilityDetail = {
          class: String(ability.class.type.name),
          fields: detail.fields(ability, "ability_detail", 0, skip)
        };
      } catch (error) {
        abilityDetail = { unresolved: String(error) };
      }
    }
    result.ability_detail = abilityDetail;
    result.special_pieces_logics = readPieceLogics(logic, detail);
    result.detail_issues = detail.issues;
    installSwapTrace();
    if (ability != null && String(ability.class.type.name) === "Match3Engine.CleoCadabra") {
      installCleoTrace();
    } else {
      removeCleoTrace();
    }
    if (ability != null && String(ability.class.type.name) === "Match3Engine.WoollyWorkout") {
      installWoollyTrace();
    } else {
      removeWoollyTrace();
    }
    if (ability != null && String(ability.class.type.name) === "Match3Engine.CheckmateCharles") {
      installCharlesTrace();
    } else {
      removeCharlesTrace();
    }
    const traced = ["Match3Engine.CheckmateCharles", "Match3Engine.WoollyWorkout", "Match3Engine.CleoCadabra"];
    if (ability != null && !traced.includes(String(ability.class.type.name))) {
      installBoosterTrace(ability);
    } else {
      removeBoosterTrace();
    }
    if (boosterTraceError != null) result.booster_trace_error = boosterTraceError;
    const last = [...swapTraceHistory].reverse().find((trace) => trace.logic_key === key);
    if (last != null) {
      const { logic: _logic, board: _board, ...plain } = last;
      result.swap_trace = { ...plain, events: [...last.events] };
    }
    if (swapTraceError != null) result.swap_trace_error = swapTraceError;
    if (cleoTraceError != null) result.cleo_trace_error = cleoTraceError;
    if (woollyTraceError != null) result.woolly_trace_error = woollyTraceError;
    if (charlesTraceError != null) result.charles_trace_error = charlesTraceError;
  }
  const staticChanged = key !== cachedProfileKey;
  if (withStatic || staticChanged) {
    const config = fieldValue(logic, "<configData>k__BackingField");
    cachedProfileStatic = {
      rules: reader.value(fieldValue(logic, "gameRules"), "rules"),
      config: config == null ? null : reader.fields(config, "config", 0, PROFILE_CONFIG_SKIP)
    };
    cachedProfileKey = key;
    Object.assign(result, cachedProfileStatic);
  }
  result.issues = reader.issues;
  result.consistent = counterBefore === fieldValue(rng, "<counter>k__BackingField");
  return result;
}
rpc.exports = {
  armMixyTrace() {
    return performAsync(() => {
      mixyTraceArmed = true;
    });
  },
  /** The last traced moves, also after the match ended (matchProfile then
   *  refuses): a merge played as the match's last move never reached a
   *  resting board, so no record carried its swap_trace. */
  swapTraceHistory() {
    return performAsync(() => ({
      traces: swapTraceHistory.map((trace) => {
        const { logic: _logic, board: _board, ...plain } = trace;
        return { ...plain, events: [...trace.events] };
      }),
      error: swapTraceError
    }));
  },
  /** "Snimaj svaki potez": add ability_detail and special_pieces_logics to matchProfile. */
  armBoosterDetail(on) {
    return performAsync(() => {
      boosterDetailArmed = Boolean(on);
    });
  },
  /** This match's spawn weights, refill/score overrides, gameColors and RNG.
   *
   *  `full` re-sends the per-match part (rules + config) even when it was
   *  already sent for this GameLogic; otherwise only the first call of a
   *  match carries it. Field reads only, see profileReader. */
  matchProfile(full) {
    return performAsync(() => readMatchProfile(Boolean(full)));
  },
  /** What one heap walk actually costs, without opening the poll.
   *
   *  `resolveGameLogic` is the only expensive thing the agent does: outside
   *  a match nothing is cached, so every call pays a full
   *  `Il2Cpp.gc.choose` over the IL2CPP heap. This measures that cost in
   *  the lobby and in a match, plus the cost of one whole snapshot, so the
   *  idle poll interval is chosen from numbers rather than from a guess. */
  probe(withSnapshot) {
    return performAsync(() => {
      const result = {
        ready,
        cached: cachedGameLogic != null,
        cached_valid: cachedGameLogic != null && hasBoard(cachedGameLogic)
      };
      const staticStart = Date.now();
      try {
        const field = gameLogicClass == null ? null : gameLogicClass.tryField("GameCount");
        result.game_count = field == null ? null : asNumber(field.value);
      } catch (error) {
        result.game_count_error = String(error);
      }
      result.static_read_ms = Date.now() - staticStart;
      const previousCache = cachedGameLogic;
      cachedGameLogic = null;
      const chooseStart = Date.now();
      let instances = [];
      try {
        instances = gameLogicClass == null ? [] : chooseInstances(gameLogicClass, "probe");
        result.choose_ms = Date.now() - chooseStart;
        result.instances = instances.length;
        const active = instances.filter(hasBoard);
        result.active = active.length;
        result.in_match = active.length > 0;
        if (active.length > 0) {
          cachedGameLogic = active[active.length - 1];
          const logic = cachedGameLogic;
          const readField = (name) => {
            try {
              const field = logic.tryField(name);
              return field == null ? null : asNumber(field.value);
            } catch (_) {
              return null;
            }
          };
          result.game_state_field = readField("currentGameState");
          result.game_state = readGameStateEnum(logic);
          result.moves = readField("moves");
          result.turns = readField("<Turns>k__BackingField");
          result.turns_total = readField("<TurnsTotal>k__BackingField");
          result.current_player = readField("currentPlayerIndex");
          result.game_index = readField("<GameIndex>k__BackingField");
          try {
            const players = logic.tryField("players");
            const value = players == null ? null : players.value;
            result.players = value == null || value.isNull?.() ? null : asNumber(value.field("_size").value);
          } catch (_) {
            result.players = null;
          }
        }
      } catch (error) {
        result.choose_ms = Date.now() - chooseStart;
        result.error = String(error);
        result.in_match = false;
      }
      if (withSnapshot && result.in_match) {
        const snapshotStart = Date.now();
        try {
          const snapshot = buildSnapshot("probe", true);
          result.snapshot_ms = Date.now() - snapshotStart;
          result.rows = snapshot.rows;
          result.columns = snapshot.columns;
        } catch (error) {
          result.snapshot_ms = Date.now() - snapshotStart;
          result.snapshot_error = String(error);
        }
      }
      result.polling = pollTimer != null;
      result.match_active = matchActive;
      result.ctor_hook = ctorHookState;
      result.ctor_hook_error = ctorHookError;
      result.constructed = constructedCount;
      result.resolve_by_hook = resolveByHook;
      result.resolve_by_choose = resolveByChoose;
      if (matchActive && previousCache != null) cachedGameLogic = previousCache;
      return result;
    });
  },
  dumpBoard() {
    return performAsync(() => {
      const snapshot = buildSnapshot("manual_rpc", true);
      candidateSignature = snapshot.signature;
      candidateCount = requiredStableSamples;
      sendSnapshot(snapshot, true);
      return snapshot;
    });
  },
  status() {
    return performAsync(() => ({
      ready,
      matchActive,
      ctorHook: ctorHookState,
      ctorHookError,
      concedeHook: concedeHookState,
      concedeHookError,
      disposeHook: disposeHookState,
      disposeHookError,
      disposed: disposedCount,
      disposedAgoMs: disposedAt == null ? null : Date.now() - disposedAt,
      endedLogicHandle,
      quietSignature,
      deadLogicKeys: Array.from(deadLogicKeys),
      constructed: constructedCount,
      resolveByHook,
      resolveByChoose,
      deferredResolves,
      gameCount: lastGameCount,
      quietMs: Date.now() - lastChangeTimestamp,
      gameLogicFound: (() => {
        try {
          resolveGameLogic();
          return true;
        } catch (_) {
          return false;
        }
      })(),
      pollMilliseconds,
      idleMilliseconds,
      requiredStableSamples,
      candidateCount,
      lastSentSignature,
      lastSentStateSignature,
      lastError
    }));
  },
  configure(pollMs, stableSamples, withState, idleMs, quietMs, withCtorHook) {
    return performAsync(() => {
      pollMilliseconds = Math.max(100, Math.min(1e4, Number(pollMs) || 250));
      requiredStableSamples = Math.max(2, Math.min(20, Number(stableSamples) || 3));
      includeState = withState == null ? includeState : Boolean(withState);
      if (idleMs != null) idleMilliseconds = Math.max(200, Math.min(1e4, Number(idleMs) || 1e3));
      if (quietMs != null) idleAfterQuietMs = Math.max(0, Number(quietMs));
      if (withCtorHook != null) useCtorHook = Boolean(withCtorHook);
      installDisposeHook();
      if (useCtorHook) {
        ctorHookDetachPending = false;
        installCtorHook();
      } else if (ctorHookListeners.length > 0) {
        removeCtorHook();
      }
      candidateSignature = null;
      candidateCount = 0;
      lastGameCount = null;
      startPolling();
      return {
        pollMilliseconds,
        idleMilliseconds,
        idleAfterQuietMs,
        requiredStableSamples,
        includeState,
        traceMode,
        matchActive,
        ctorHook: ctorHookState,
        ctorHookError,
        concedeHook: concedeHookState,
        concedeHookError,
        disposeHook: disposeHookState,
        disposeHookError
      };
    });
  },
  /** Pick up a match that is already in progress, on the host's say-so.
   *
   *  The idle path deliberately refuses to guess -- a finished match looks
   *  exactly like a running one on the heap. This is the other half of that
   *  decision: when the user asks for a move, the engine's own state is
   *  allowed to answer, because the user is looking at the screen and the
   *  agent is not. */
  wake() {
    return performAsync(() => {
      idleChooseAfter = 0;
      lastGameCount = readGameCount();
      const detail = { game_count: lastGameCount };
      let logic = null;
      try {
        logic = resolveGameLogic();
        detail.found = true;
      } catch (error) {
        detail.found = false;
        detail.resolve_error = String(error);
        const revived = reviveNewestDeadLogic();
        if (revived != null) {
          logic = revived;
          detail.found = true;
          detail.revived = true;
          send({
            type: "error",
            stage: "wake",
            message: "ozivljavam partiju koju je host ranije obelezio kao zavrsenu: korisnik trazi potez, a engine kaze da traje"
          });
        }
      }
      if (logic != null) {
        detail.state = readGameStateEnum(logic);
        detail.state_raw = (() => {
          try {
            return logic.handle.add(EXPECTED_OFFSETS["GameLogic.currentGameState"]).readS32();
          } catch (_) {
            return null;
          }
        })();
        detail.has_board = hasBoard(logic);
        detail.simulation = isSimulation(logic);
      }
      if (!matchActive && matchIsRunning()) setMatchActive(true, "rucno");
      detail.match_active = matchActive;
      return detail;
    });
  },
  /** The user says the match is over (a concede the engine did not report).
   *
   *  Goes through the same edge as a natural end, so the host gets the same
   *  `match_state` message and the idle tick takes over -- the next match is
   *  then picked up by the counter, exactly as after a normal finish. */
  /** Matches the host knows are over: GameLogic/board keys from its own
   *  record of earlier ends, in this same game process. A fresh agent has
   *  no memory of them and would take the last match's corpse for a running
   *  one; called before configure() so the first idle tick already knows.
   *  If the match currently being read is among them, it is closed. */
  markDead(keys) {
    return performAsync(() => {
      for (const key of keys || []) {
        if (typeof key === "string" && key.length > 0) markLogicDead(key);
      }
      if (matchActive && cachedGameLogic != null && isDeadLogic(cachedGameLogic)) {
        quietSignature = lastSentSignature;
        setMatchActive(false, "partija iz prethodne sesije");
      }
      return { dead: deadLogicKeys.size, match_active: matchActive };
    });
  },
  endMatch(reason) {
    return performAsync(() => {
      const wasActive = matchActive;
      quietSignature = lastSentSignature;
      setMatchActive(false, String(reason || "rucno prekinuta"));
      return { was_active: wasActive, match_active: matchActive, game_count: lastGameCount };
    });
  },
  setTrace(enabled, pollMs) {
    return performAsync(() => {
      traceMode = Boolean(enabled);
      if (pollMs != null) {
        pollMilliseconds = Math.max(20, Math.min(1e4, Number(pollMs) || 250));
        startPolling();
      }
      return { traceMode, pollMilliseconds };
    });
  }
};
setImmediate(() => {
  Il2Cpp.perform(() => {
    try {
      initializeMetadata();
      ready = true;
      send({
        type: "ready",
        application: Il2Cpp.application.identifier,
        version: Il2Cpp.application.version,
        unity: Il2Cpp.unityVersion,
        poll_milliseconds: pollMilliseconds,
        stable_samples: requiredStableSamples
      });
    } catch (error) {
      lastError = String(error);
      send({ type: "error", stage: "initialize", message: lastError });
    }
  });
});
