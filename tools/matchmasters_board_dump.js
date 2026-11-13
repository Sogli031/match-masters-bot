📦
255464 /tools/matchmasters_board_dump.js
156609 /tools/matchmasters_board_dump.js.map
✄
// tools/node_modules/frida-il2cpp-bridge/dist/index.js
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

// tools/matchmasters_board_dump.ts
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
    const cleoLogic = image.class("Match3Engine.CleoCadabraPieceLogic");
    const cleoSwap = address(cleoLogic, "SwapPerformed", 3);
    const cleoConvert = address(cleoLogic, "ConvertToPiece", 1);
    const allCombos = address(analyzer, "GetAllCombos", 4);
    const chance = address(image.class("Match3Engine.RandomWrapper"), "Chance", 1);
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
    swapTraceListeners = listeners;
  } catch (error) {
    for (const listener of listeners) listener.detach();
    swapTraceError = String(error);
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
    const last = [...swapTraceHistory].reverse().find((trace) => trace.logic_key === key);
    if (last != null) {
      const { logic: _logic, board: _board, ...plain } = last;
      result.swap_trace = { ...plain, events: [...last.events] };
    }
    if (swapTraceError != null) result.swap_trace_error = swapTraceError;
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

✄
{
  "version": 3,
  "sources": ["tools/node_modules/frida-il2cpp-bridge/dist/application.ts", "tools/node_modules/frida-il2cpp-bridge/dist/boxed.ts", "tools/node_modules/frida-il2cpp-bridge/dist/config.ts", "tools/node_modules/frida-il2cpp-bridge/dist/dump.ts", "tools/node_modules/frida-il2cpp-bridge/dist/exception-listener.ts", "tools/node_modules/frida-il2cpp-bridge/dist/exports.ts", "tools/node_modules/frida-il2cpp-bridge/dist/filters.ts", "tools/node_modules/frida-il2cpp-bridge/dist/gc.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/android.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/console.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/decorate.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/getter.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/hash.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/lazy.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/native-struct.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/object.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/offset-of.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/read-native-iterator.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/read-native-list.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/recycle.ts", "tools/node_modules/frida-il2cpp-bridge/dist/utils/unity-version.ts", "tools/node_modules/frida-il2cpp-bridge/dist/memory.ts", "tools/node_modules/frida-il2cpp-bridge/dist/module.ts", "tools/node_modules/frida-il2cpp-bridge/dist/nullable.ts", "tools/node_modules/frida-il2cpp-bridge/dist/perform.ts", "tools/node_modules/frida-il2cpp-bridge/dist/tracer.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/array.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/assembly.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/class.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/delegate.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/domain.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/field.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/gc-handle.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/image.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/memory-snapshot.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/method.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/object.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/parameter.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/pointer.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/reference.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/string.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/thread.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/type.ts", "tools/node_modules/frida-il2cpp-bridge/dist/structs/value-type.ts", "tools/node_modules/frida-il2cpp-bridge/dist/index.ts", "tools/matchmasters_board_dump.ts"],
  "mappings": "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",
  "names": ["Il2Cpp", "Android", "getter", "obj", "UnityVersion", "a", "b", "_", "module", "parameters", "method", "Array", "array", "delegate", "memorySnapshot", "i", "Object", "field", "String", "value", "_", "getter", "_", "refill"]
}
