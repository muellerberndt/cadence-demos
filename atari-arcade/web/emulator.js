// emulator.js: the 6502.ts Atari 2600 core (MIT, Christian Speckner and contributors) bundled with the arcade's game interface. Built from emulator/ale.js; do not edit by hand.
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __esm = (fn, res) => function __init() {
  return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
};
var __commonJS = (cb, mod) => function __require() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// node_modules/tslib/tslib.es6.mjs
var tslib_es6_exports = {};
__export(tslib_es6_exports, {
  __addDisposableResource: () => __addDisposableResource,
  __assign: () => __assign,
  __asyncDelegator: () => __asyncDelegator,
  __asyncGenerator: () => __asyncGenerator,
  __asyncValues: () => __asyncValues,
  __await: () => __await,
  __awaiter: () => __awaiter,
  __classPrivateFieldGet: () => __classPrivateFieldGet,
  __classPrivateFieldIn: () => __classPrivateFieldIn,
  __classPrivateFieldSet: () => __classPrivateFieldSet,
  __createBinding: () => __createBinding,
  __decorate: () => __decorate,
  __disposeResources: () => __disposeResources,
  __esDecorate: () => __esDecorate,
  __exportStar: () => __exportStar,
  __extends: () => __extends,
  __generator: () => __generator,
  __importDefault: () => __importDefault,
  __importStar: () => __importStar,
  __makeTemplateObject: () => __makeTemplateObject,
  __metadata: () => __metadata,
  __param: () => __param,
  __propKey: () => __propKey,
  __read: () => __read,
  __rest: () => __rest,
  __rewriteRelativeImportExtension: () => __rewriteRelativeImportExtension,
  __runInitializers: () => __runInitializers,
  __setFunctionName: () => __setFunctionName,
  __spread: () => __spread,
  __spreadArray: () => __spreadArray,
  __spreadArrays: () => __spreadArrays,
  __values: () => __values,
  default: () => tslib_es6_default
});
function __extends(d, b) {
  if (typeof b !== "function" && b !== null)
    throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
  extendStatics(d, b);
  function __() {
    this.constructor = d;
  }
  d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
}
function __rest(s, e) {
  var t = {};
  for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
    t[p] = s[p];
  if (s != null && typeof Object.getOwnPropertySymbols === "function")
    for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
      if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
        t[p[i]] = s[p[i]];
    }
  return t;
}
function __decorate(decorators, target, key, desc) {
  var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
  if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
  else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
  return c > 3 && r && Object.defineProperty(target, key, r), r;
}
function __param(paramIndex, decorator) {
  return function(target, key) {
    decorator(target, key, paramIndex);
  };
}
function __esDecorate(ctor, descriptorIn, decorators, contextIn, initializers, extraInitializers) {
  function accept(f) {
    if (f !== void 0 && typeof f !== "function") throw new TypeError("Function expected");
    return f;
  }
  var kind = contextIn.kind, key = kind === "getter" ? "get" : kind === "setter" ? "set" : "value";
  var target = !descriptorIn && ctor ? contextIn["static"] ? ctor : ctor.prototype : null;
  var descriptor = descriptorIn || (target ? Object.getOwnPropertyDescriptor(target, contextIn.name) : {});
  var _, done = false;
  for (var i = decorators.length - 1; i >= 0; i--) {
    var context = {};
    for (var p in contextIn) context[p] = p === "access" ? {} : contextIn[p];
    for (var p in contextIn.access) context.access[p] = contextIn.access[p];
    context.addInitializer = function(f) {
      if (done) throw new TypeError("Cannot add initializers after decoration has completed");
      extraInitializers.push(accept(f || null));
    };
    var result = (0, decorators[i])(kind === "accessor" ? { get: descriptor.get, set: descriptor.set } : descriptor[key], context);
    if (kind === "accessor") {
      if (result === void 0) continue;
      if (result === null || typeof result !== "object") throw new TypeError("Object expected");
      if (_ = accept(result.get)) descriptor.get = _;
      if (_ = accept(result.set)) descriptor.set = _;
      if (_ = accept(result.init)) initializers.unshift(_);
    } else if (_ = accept(result)) {
      if (kind === "field") initializers.unshift(_);
      else descriptor[key] = _;
    }
  }
  if (target) Object.defineProperty(target, contextIn.name, descriptor);
  done = true;
}
function __runInitializers(thisArg, initializers, value) {
  var useValue = arguments.length > 2;
  for (var i = 0; i < initializers.length; i++) {
    value = useValue ? initializers[i].call(thisArg, value) : initializers[i].call(thisArg);
  }
  return useValue ? value : void 0;
}
function __propKey(x) {
  return typeof x === "symbol" ? x : "".concat(x);
}
function __setFunctionName(f, name, prefix) {
  if (typeof name === "symbol") name = name.description ? "[".concat(name.description, "]") : "";
  return Object.defineProperty(f, "name", { configurable: true, value: prefix ? "".concat(prefix, " ", name) : name });
}
function __metadata(metadataKey, metadataValue) {
  if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(metadataKey, metadataValue);
}
function __awaiter(thisArg, _arguments, P, generator) {
  function adopt(value) {
    return value instanceof P ? value : new P(function(resolve) {
      resolve(value);
    });
  }
  return new (P || (P = Promise))(function(resolve, reject) {
    function fulfilled(value) {
      try {
        step(generator.next(value));
      } catch (e) {
        reject(e);
      }
    }
    function rejected(value) {
      try {
        step(generator["throw"](value));
      } catch (e) {
        reject(e);
      }
    }
    function step(result) {
      result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
    }
    step((generator = generator.apply(thisArg, _arguments || [])).next());
  });
}
function __generator(thisArg, body) {
  var _ = { label: 0, sent: function() {
    if (t[0] & 1) throw t[1];
    return t[1];
  }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
  return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() {
    return this;
  }), g;
  function verb(n) {
    return function(v) {
      return step([n, v]);
    };
  }
  function step(op) {
    if (f) throw new TypeError("Generator is already executing.");
    while (g && (g = 0, op[0] && (_ = 0)), _) try {
      if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
      if (y = 0, t) op = [op[0] & 2, t.value];
      switch (op[0]) {
        case 0:
        case 1:
          t = op;
          break;
        case 4:
          _.label++;
          return { value: op[1], done: false };
        case 5:
          _.label++;
          y = op[1];
          op = [0];
          continue;
        case 7:
          op = _.ops.pop();
          _.trys.pop();
          continue;
        default:
          if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
            _ = 0;
            continue;
          }
          if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
            _.label = op[1];
            break;
          }
          if (op[0] === 6 && _.label < t[1]) {
            _.label = t[1];
            t = op;
            break;
          }
          if (t && _.label < t[2]) {
            _.label = t[2];
            _.ops.push(op);
            break;
          }
          if (t[2]) _.ops.pop();
          _.trys.pop();
          continue;
      }
      op = body.call(thisArg, _);
    } catch (e) {
      op = [6, e];
      y = 0;
    } finally {
      f = t = 0;
    }
    if (op[0] & 5) throw op[1];
    return { value: op[0] ? op[1] : void 0, done: true };
  }
}
function __exportStar(m, o) {
  for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(o, p)) __createBinding(o, m, p);
}
function __values(o) {
  var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
  if (m) return m.call(o);
  if (o && typeof o.length === "number") return {
    next: function() {
      if (o && i >= o.length) o = void 0;
      return { value: o && o[i++], done: !o };
    }
  };
  throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
}
function __read(o, n) {
  var m = typeof Symbol === "function" && o[Symbol.iterator];
  if (!m) return o;
  var i = m.call(o), r, ar = [], e;
  try {
    while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
  } catch (error) {
    e = { error };
  } finally {
    try {
      if (r && !r.done && (m = i["return"])) m.call(i);
    } finally {
      if (e) throw e.error;
    }
  }
  return ar;
}
function __spread() {
  for (var ar = [], i = 0; i < arguments.length; i++)
    ar = ar.concat(__read(arguments[i]));
  return ar;
}
function __spreadArrays() {
  for (var s = 0, i = 0, il = arguments.length; i < il; i++) s += arguments[i].length;
  for (var r = Array(s), k = 0, i = 0; i < il; i++)
    for (var a = arguments[i], j = 0, jl = a.length; j < jl; j++, k++)
      r[k] = a[j];
  return r;
}
function __spreadArray(to, from, pack) {
  if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
    if (ar || !(i in from)) {
      if (!ar) ar = Array.prototype.slice.call(from, 0, i);
      ar[i] = from[i];
    }
  }
  return to.concat(ar || Array.prototype.slice.call(from));
}
function __await(v) {
  return this instanceof __await ? (this.v = v, this) : new __await(v);
}
function __asyncGenerator(thisArg, _arguments, generator) {
  if (!Symbol.asyncIterator) throw new TypeError("Symbol.asyncIterator is not defined.");
  var g = generator.apply(thisArg, _arguments || []), i, q = [];
  return i = Object.create((typeof AsyncIterator === "function" ? AsyncIterator : Object).prototype), verb("next"), verb("throw"), verb("return", awaitReturn), i[Symbol.asyncIterator] = function() {
    return this;
  }, i;
  function awaitReturn(f) {
    return function(v) {
      return Promise.resolve(v).then(f, reject);
    };
  }
  function verb(n, f) {
    if (g[n]) {
      i[n] = function(v) {
        return new Promise(function(a, b) {
          q.push([n, v, a, b]) > 1 || resume(n, v);
        });
      };
      if (f) i[n] = f(i[n]);
    }
  }
  function resume(n, v) {
    try {
      step(g[n](v));
    } catch (e) {
      settle(q[0][3], e);
    }
  }
  function step(r) {
    r.value instanceof __await ? Promise.resolve(r.value.v).then(fulfill, reject) : settle(q[0][2], r);
  }
  function fulfill(value) {
    resume("next", value);
  }
  function reject(value) {
    resume("throw", value);
  }
  function settle(f, v) {
    if (f(v), q.shift(), q.length) resume(q[0][0], q[0][1]);
  }
}
function __asyncDelegator(o) {
  var i, p;
  return i = {}, verb("next"), verb("throw", function(e) {
    throw e;
  }), verb("return"), i[Symbol.iterator] = function() {
    return this;
  }, i;
  function verb(n, f) {
    i[n] = o[n] ? function(v) {
      return (p = !p) ? { value: __await(o[n](v)), done: false } : f ? f(v) : v;
    } : f;
  }
}
function __asyncValues(o) {
  if (!Symbol.asyncIterator) throw new TypeError("Symbol.asyncIterator is not defined.");
  var m = o[Symbol.asyncIterator], i;
  return m ? m.call(o) : (o = typeof __values === "function" ? __values(o) : o[Symbol.iterator](), i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function() {
    return this;
  }, i);
  function verb(n) {
    i[n] = o[n] && function(v) {
      return new Promise(function(resolve, reject) {
        v = o[n](v), settle(resolve, reject, v.done, v.value);
      });
    };
  }
  function settle(resolve, reject, d, v) {
    Promise.resolve(v).then(function(v2) {
      resolve({ value: v2, done: d });
    }, reject);
  }
}
function __makeTemplateObject(cooked, raw) {
  if (Object.defineProperty) {
    Object.defineProperty(cooked, "raw", { value: raw });
  } else {
    cooked.raw = raw;
  }
  return cooked;
}
function __importStar(mod) {
  if (mod && mod.__esModule) return mod;
  var result = {};
  if (mod != null) {
    for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
  }
  __setModuleDefault(result, mod);
  return result;
}
function __importDefault(mod) {
  return mod && mod.__esModule ? mod : { default: mod };
}
function __classPrivateFieldGet(receiver, state, kind, f) {
  if (kind === "a" && !f) throw new TypeError("Private accessor was defined without a getter");
  if (typeof state === "function" ? receiver !== state || !f : !state.has(receiver)) throw new TypeError("Cannot read private member from an object whose class did not declare it");
  return kind === "m" ? f : kind === "a" ? f.call(receiver) : f ? f.value : state.get(receiver);
}
function __classPrivateFieldSet(receiver, state, value, kind, f) {
  if (kind === "m") throw new TypeError("Private method is not writable");
  if (kind === "a" && !f) throw new TypeError("Private accessor was defined without a setter");
  if (typeof state === "function" ? receiver !== state || !f : !state.has(receiver)) throw new TypeError("Cannot write private member to an object whose class did not declare it");
  return kind === "a" ? f.call(receiver, value) : f ? f.value = value : state.set(receiver, value), value;
}
function __classPrivateFieldIn(state, receiver) {
  if (receiver === null || typeof receiver !== "object" && typeof receiver !== "function") throw new TypeError("Cannot use 'in' operator on non-object");
  return typeof state === "function" ? receiver === state : state.has(receiver);
}
function __addDisposableResource(env, value, async) {
  if (value !== null && value !== void 0) {
    if (typeof value !== "object" && typeof value !== "function") throw new TypeError("Object expected.");
    var dispose, inner;
    if (async) {
      if (!Symbol.asyncDispose) throw new TypeError("Symbol.asyncDispose is not defined.");
      dispose = value[Symbol.asyncDispose];
    }
    if (dispose === void 0) {
      if (!Symbol.dispose) throw new TypeError("Symbol.dispose is not defined.");
      dispose = value[Symbol.dispose];
      if (async) inner = dispose;
    }
    if (typeof dispose !== "function") throw new TypeError("Object not disposable.");
    if (inner) dispose = function() {
      try {
        inner.call(this);
      } catch (e) {
        return Promise.reject(e);
      }
    };
    env.stack.push({ value, dispose, async });
  } else if (async) {
    env.stack.push({ async: true });
  }
  return value;
}
function __disposeResources(env) {
  function fail(e) {
    env.error = env.hasError ? new _SuppressedError(e, env.error, "An error was suppressed during disposal.") : e;
    env.hasError = true;
  }
  var r, s = 0;
  function next() {
    while (r = env.stack.pop()) {
      try {
        if (!r.async && s === 1) return s = 0, env.stack.push(r), Promise.resolve().then(next);
        if (r.dispose) {
          var result = r.dispose.call(r.value);
          if (r.async) return s |= 2, Promise.resolve(result).then(next, function(e) {
            fail(e);
            return next();
          });
        } else s |= 1;
      } catch (e) {
        fail(e);
      }
    }
    if (s === 1) return env.hasError ? Promise.reject(env.error) : Promise.resolve();
    if (env.hasError) throw env.error;
  }
  return next();
}
function __rewriteRelativeImportExtension(path, preserveJsx) {
  if (typeof path === "string" && /^\.\.?\//.test(path)) {
    return path.replace(/\.(tsx)$|((?:\.d)?)((?:\.[^./]+?)?)\.([cm]?)ts$/i, function(m, tsx, d, ext, cm) {
      return tsx ? preserveJsx ? ".jsx" : ".js" : d && (!ext || !cm) ? m : d + ext + "." + cm.toLowerCase() + "js";
    });
  }
  return path;
}
var extendStatics, __assign, __createBinding, __setModuleDefault, ownKeys, _SuppressedError, tslib_es6_default;
var init_tslib_es6 = __esm({
  "node_modules/tslib/tslib.es6.mjs"() {
    extendStatics = function(d, b) {
      extendStatics = Object.setPrototypeOf || { __proto__: [] } instanceof Array && function(d2, b2) {
        d2.__proto__ = b2;
      } || function(d2, b2) {
        for (var p in b2) if (Object.prototype.hasOwnProperty.call(b2, p)) d2[p] = b2[p];
      };
      return extendStatics(d, b);
    };
    __assign = function() {
      __assign = Object.assign || function __assign2(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
          s = arguments[i];
          for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
        }
        return t;
      };
      return __assign.apply(this, arguments);
    };
    __createBinding = Object.create ? function(o, m, k, k2) {
      if (k2 === void 0) k2 = k;
      var desc = Object.getOwnPropertyDescriptor(m, k);
      if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
        desc = { enumerable: true, get: function() {
          return m[k];
        } };
      }
      Object.defineProperty(o, k2, desc);
    } : function(o, m, k, k2) {
      if (k2 === void 0) k2 = k;
      o[k2] = m[k];
    };
    __setModuleDefault = Object.create ? function(o, v) {
      Object.defineProperty(o, "default", { enumerable: true, value: v });
    } : function(o, v) {
      o["default"] = v;
    };
    ownKeys = function(o) {
      ownKeys = Object.getOwnPropertyNames || function(o2) {
        var ar = [];
        for (var k in o2) if (Object.prototype.hasOwnProperty.call(o2, k)) ar[ar.length] = k;
        return ar;
      };
      return ownKeys(o);
    };
    _SuppressedError = typeof SuppressedError === "function" ? SuppressedError : function(error, suppressed, message) {
      var e = new Error(message);
      return e.name = "SuppressedError", e.error = error, e.suppressed = suppressed, e;
    };
    tslib_es6_default = {
      __extends,
      __assign,
      __rest,
      __decorate,
      __param,
      __esDecorate,
      __runInitializers,
      __propKey,
      __setFunctionName,
      __metadata,
      __awaiter,
      __generator,
      __createBinding,
      __exportStar,
      __values,
      __read,
      __spread,
      __spreadArrays,
      __spreadArray,
      __await,
      __asyncGenerator,
      __asyncDelegator,
      __asyncValues,
      __makeTemplateObject,
      __importStar,
      __importDefault,
      __classPrivateFieldGet,
      __classPrivateFieldSet,
      __classPrivateFieldIn,
      __addDisposableResource,
      __disposeResources,
      __rewriteRelativeImportExtension
    };
  }
});

// node_modules/microevent.ts/lib/Event.js
var require_Event = __commonJS({
  "node_modules/microevent.ts/lib/Event.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var factories = [];
    factories[0] = function() {
      return function dispatcher0() {
      };
    };
    factories[1] = function(callback, context) {
      if (typeof context === "undefined")
        return callback;
      return function dispatcher1(payload) {
        callback(payload, context);
      };
    };
    function getFactory(handlerCount) {
      if (!factories[handlerCount])
        factories[handlerCount] = compileFactory(handlerCount);
      return factories[handlerCount];
    }
    function compileFactory(handlerCount) {
      var src = "return function dispatcher" + handlerCount + "(payload) {\n";
      var argsHandlers = [], argsContexts = [];
      for (var i = 0; i < handlerCount; i++) {
        argsHandlers.push("cb" + i);
        argsContexts.push("ctx" + i);
        src += "    cb" + i + "(payload, ctx" + i + ");\n";
      }
      src += "};";
      return new (Function.bind.apply(Function, [void 0].concat(argsHandlers.concat(argsContexts), [src])))();
    }
    var Event = (
      /** @class */
      function() {
        function Event2() {
          this.hasHandlers = false;
          this._handlers = [];
          this._contexts = [];
          this._createDispatcher();
        }
        Event2.prototype.addHandler = function(handler, context) {
          if (!this.isHandlerAttached(handler, context)) {
            this._handlers.push(handler);
            this._contexts.push(context);
            this._createDispatcher();
            this._updateHasHandlers();
          }
          return this;
        };
        Event2.prototype.removeHandler = function(handler, context) {
          var idx = this._getHandlerIndex(handler, context);
          if (typeof idx !== "undefined") {
            this._handlers.splice(idx, 1);
            this._contexts.splice(idx, 1);
            this._createDispatcher();
            this._updateHasHandlers();
          }
          return this;
        };
        Event2.prototype.isHandlerAttached = function(handler, context) {
          return typeof this._getHandlerIndex(handler, context) !== "undefined";
        };
        Event2.prototype._updateHasHandlers = function() {
          this.hasHandlers = !!this._handlers.length;
        };
        Event2.prototype._getHandlerIndex = function(handler, context) {
          var handlerCount = this._handlers.length;
          var idx;
          for (idx = 0; idx < handlerCount; idx++) {
            if (this._handlers[idx] === handler && this._contexts[idx] === context)
              break;
          }
          return idx < handlerCount ? idx : void 0;
        };
        Event2.prototype._createDispatcher = function() {
          this.dispatch = getFactory(this._handlers.length).apply(this, this._handlers.concat(this._contexts));
        };
        return Event2;
      }()
    );
    exports.default = Event;
  }
});

// node_modules/microevent.ts/lib/index.js
var require_lib = __commonJS({
  "node_modules/microevent.ts/lib/index.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var Event_1 = require_Event();
    exports.Event = Event_1.default;
  }
});

// node_modules/6502.ts/lib/machine/board/BoardInterface.js
var require_BoardInterface = __commonJS({
  "node_modules/6502.ts/lib/machine/board/BoardInterface.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var BoardInterface;
    (function(BoardInterface2) {
      class TrapPayload {
        constructor(reason, board, message) {
          this.reason = reason;
          this.board = board;
          this.message = message;
        }
      }
      BoardInterface2.TrapPayload = TrapPayload;
    })(BoardInterface || (BoardInterface = {}));
    exports.default = BoardInterface;
  }
});

// node_modules/6502.ts/lib/machine/stella/Bus.js
var require_Bus = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/Bus.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var microevent_ts_1 = require_lib();
    var Bus = class _Bus {
      constructor() {
        this.event = {
          trap: new microevent_ts_1.Event(),
          read: new microevent_ts_1.Event(),
          write: new microevent_ts_1.Event(),
          transition: new microevent_ts_1.Event()
        };
        this._tia = null;
        this._pia = null;
        this._cartridge = null;
        this._lastDataBusValue = 0;
        this._lastAddressBusValue = 0;
      }
      setTia(tia) {
        tia.trap.addHandler((payload) => this.triggerTrap(0, "TIA: " + (payload.message || "")));
        this._tia = tia;
        return this;
      }
      setPia(pia) {
        pia.trap.addHandler((payload) => this.triggerTrap(1, "PIA: " + (payload.message || "")));
        this._pia = pia;
        return this;
      }
      setCartridge(cartridge) {
        cartridge.trap.addHandler((payload) => this.triggerTrap(2, "CARTRIDGE: " + (payload.message || "")));
        this._cartridge = cartridge;
        return this;
      }
      readWord(address) {
        return this.read(address) | this.read(address + 1 & 65535) << 8;
      }
      read(address) {
        address &= 8191;
        this.event.transition.dispatch(address);
        this._lastAddressBusValue = address;
        if (address & 4096) {
          this._lastDataBusValue = this._cartridge.read(address);
          this.event.read.dispatch(2);
        } else if (address & 128) {
          this._lastDataBusValue = this._pia.read(address);
          this.event.read.dispatch(1);
        } else {
          this._lastDataBusValue = this._tia.read(address);
          this.event.read.dispatch(0);
        }
        return this._lastDataBusValue;
      }
      write(address, value) {
        this._lastDataBusValue = value;
        address &= 8191;
        this.event.transition.dispatch(address);
        this._lastAddressBusValue = address;
        if (address & 4096) {
          this._cartridge.write(address, value);
          this.event.write.dispatch(2);
        } else if (address & 128) {
          this._pia.write(address, value);
          this.event.write.dispatch(1);
        } else {
          this._tia.write(address, value);
          this.event.write.dispatch(0);
        }
      }
      peek(address) {
        address &= 8191;
        if (address & 4096) {
          return this._cartridge.peek(address);
        } else if (address & 128) {
          return this._pia.peek(address);
        } else {
          return this._tia.peek(address);
        }
      }
      poke(address, value) {
      }
      getLastDataBusValue() {
        return this._lastDataBusValue;
      }
      setDataBusValue(value) {
        this._lastDataBusValue = value;
      }
      getLastAddresBusValue() {
        return this._lastAddressBusValue;
      }
      triggerTrap(reason, message) {
        if (this.event.trap.hasHandlers) {
          this.event.trap.dispatch(new _Bus.TrapPayload(reason, this, message));
        } else {
          throw new Error(message);
        }
      }
    };
    exports.default = Bus;
    (function(Bus2) {
      class TrapPayload {
        constructor(reason, bus, message) {
          this.reason = reason;
          this.bus = bus;
          this.message = message;
        }
      }
      Bus2.TrapPayload = TrapPayload;
    })(Bus || (Bus = {}));
    exports.default = Bus;
  }
});

// node_modules/6502.ts/lib/machine/stella/Pia.js
var require_Pia = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/Pia.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var microevent_ts_1 = require_lib();
    var Pia = class {
      constructor(_controlPanel, _joystick0, _joystick1, _rng) {
        this._controlPanel = _controlPanel;
        this._joystick0 = _joystick0;
        this._joystick1 = _joystick1;
        this._rng = _rng;
        this.trap = new microevent_ts_1.Event();
        this.ram = new Uint8Array(128);
        this._bus = null;
        this._timerValue = 255;
        this._subTimer = 0;
        this._timerDivide = 1024;
        this._interruptFlag = 0;
        this._timerWrapped = false;
        this._flagSetDuringThisCycle = false;
        this.reset();
      }
      reset() {
        for (let i = 0; i < 128; i++) {
          this.ram[i] = this._rng ? this._rng.int(255) : 0;
        }
        this._interruptFlag = 0;
        this._flagSetDuringThisCycle = false;
        this._timerDivide = 1024;
        this._subTimer = 0;
        this._rng.int(255);
        this._timerValue = 0;
        this._timerWrapped = false;
      }
      read(address) {
        if (address & 512) {
          if (address & 4) {
            return this._readTimer(address);
          } else {
            return this._readIo(address);
          }
        } else {
          return this.ram[address & 127];
        }
      }
      peek(address) {
        if (address & 512) {
          if (address & 4) {
            return this._peekTimer(address);
          } else {
            return this._readIo(address);
          }
        } else {
          return this.ram[address & 127];
        }
      }
      write(address, value) {
        if (address & 512) {
          if (address & 4) {
            return this._writeTimer(address, value);
          } else {
            return this._writeIo(address, value);
          }
        } else {
          this.ram[address & 127] = value;
        }
      }
      cycle() {
        this._cycleTimer();
      }
      getDebugState() {
        return `divider: ${this._timerDivide} raw timer: INTIM: ${this._timerValue}`;
      }
      setBus(bus) {
        this._bus = bus;
        return this;
      }
      _writeIo(address, value) {
      }
      _writeTimer(address, value) {
        this._interruptFlag = 0;
        switch (address & 663) {
          case 663:
            return this._setTimer(1024, value);
          case 662:
            return this._setTimer(64, value);
          case 661:
            return this._setTimer(8, value);
          case 660:
            return this._setTimer(1, value);
        }
      }
      _setTimer(divide, value) {
        this._timerDivide = divide;
        this._timerValue = value;
        this._subTimer = 0;
        this._timerWrapped = false;
      }
      _readIo(address) {
        switch (address & 643) {
          case 640:
            return (this._joystick1.getUp().read() ? 0 : 1) | (this._joystick1.getDown().read() ? 0 : 2) | (this._joystick1.getLeft().read() ? 0 : 4) | (this._joystick1.getRight().read() ? 0 : 8) | (this._joystick0.getUp().read() ? 0 : 16) | (this._joystick0.getDown().read() ? 0 : 32) | (this._joystick0.getLeft().read() ? 0 : 64) | (this._joystick0.getRight().read() ? 0 : 128);
          case 642:
            return (this._controlPanel.getResetButton().read() ? 0 : 1) | (this._controlPanel.getSelectSwitch().read() ? 0 : 2) | (this._controlPanel.getColorSwitch().read() ? 0 : 8) | (this._controlPanel.getDifficultySwitchP0().read() ? 0 : 64) | (this._controlPanel.getDifficultySwitchP1().read() ? 0 : 128);
        }
        return this._bus.getLastDataBusValue();
      }
      _readTimer(address) {
        if (address & 1) {
          const flag = this._interruptFlag;
          return flag & 128;
        } else {
          if (!this._flagSetDuringThisCycle) {
            this._interruptFlag = 0;
            this._timerWrapped = false;
          }
          return this._timerValue;
        }
      }
      _peekTimer(address) {
        return address & 1 ? this._interruptFlag & 128 : this._timerValue;
      }
      _cycleTimer() {
        this._flagSetDuringThisCycle = false;
        if (this._timerWrapped) {
          this._timerValue = this._timerValue + 255 & 255;
        } else if (this._subTimer === 0 && --this._timerValue < 0) {
          this._timerValue = 255;
          this._flagSetDuringThisCycle = true;
          this._interruptFlag = 255;
          this._timerWrapped = true;
        }
        if (++this._subTimer === this._timerDivide) {
          this._subTimer = 0;
        }
      }
    };
    exports.default = Pia;
    (function(Pia2) {
      class TrapPayload {
        constructor(reason, pia, message) {
          this.reason = reason;
          this.pia = pia;
          this.message = message;
        }
      }
      Pia2.TrapPayload = TrapPayload;
    })(Pia || (Pia = {}));
    exports.default = Pia;
  }
});

// node_modules/6502.ts/lib/machine/cpu/CpuInterface.js
var require_CpuInterface = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/CpuInterface.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var CpuInterface;
    (function(CpuInterface2) {
      class State {
        constructor() {
          this.a = 0;
          this.x = 0;
          this.y = 0;
          this.s = 0;
          this.p = 0;
          this.flags = 0;
          this.irq = false;
          this.nmi = false;
        }
      }
      CpuInterface2.State = State;
    })(CpuInterface || (CpuInterface = {}));
    exports.default = CpuInterface;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/ResultImpl.js
var require_ResultImpl = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/ResultImpl.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var ResultImpl = class {
      constructor() {
        this.cycleType = 0;
        this.address = 0;
        this.value = 0;
        this.pollInterrupts = false;
        this.nextStep = null;
      }
      read(nextStep, address) {
        this.cycleType = 0;
        this.address = address;
        this.nextStep = nextStep;
        return this;
      }
      write(nextStep, address, value) {
        this.cycleType = 1;
        this.address = address;
        this.value = value;
        this.nextStep = nextStep;
        return this;
      }
      poll(poll) {
        this.pollInterrupts = poll;
        return this;
      }
    };
    exports.default = ResultImpl;
  }
});

// node_modules/6502.ts/lib/tools/decorators.js
var require_decorators = __commonJS({
  "node_modules/6502.ts/lib/tools/decorators.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.Immutable = exports.freezeImmutables = void 0;
    var immutables = Symbol("immutable properties");
    function freezeImmutables(target) {
      const immutableProperties = target[immutables];
      if (!immutableProperties) {
        return;
      }
      for (const prop of immutableProperties) {
        Object.defineProperty(target, prop, { writable: false, configurable: false });
      }
    }
    exports.freezeImmutables = freezeImmutables;
    function Immutable(target, prop) {
      if (!target[immutables]) {
        Object.defineProperty(target, immutables, { value: [], writable: false, enumerable: false });
      }
      target[immutables].push(prop);
    }
    exports.Immutable = Immutable;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/vector/boot.js
var require_boot = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/vector/boot.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.boot = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Boot = class {
      constructor(state) {
        this.reset = () => this._result.read(this._pre1Step, 255);
        this._pre1Step = () => this._result.read(this._pre2Step, 255);
        this._pre2Step = () => this._result.read(this._stack1Step, 256);
        this._stack1Step = () => this._result.read(this._stack2Step, 511);
        this._stack2Step = () => {
          this._state.s = 253;
          return this._result.read(this._stack3Step, 510);
        };
        this._stack3Step = () => this._result.read(this._readTargetLoStep, 65532);
        this._readTargetLoStep = (operand) => {
          this._targetAddress = operand;
          return this._result.read(this._readTargetHiStep, 65533);
        };
        this._readTargetHiStep = (operand) => {
          this._targetAddress |= operand << 8;
          this._state.p = this._targetAddress;
          return null;
        };
        this._targetAddress = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_pre1Step", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_pre2Step", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_stack1Step", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_stack2Step", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_stack3Step", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_readTargetLoStep", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_readTargetHiStep", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Boot.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Boot.prototype, "_state", void 0);
    var boot = (state) => new Boot(state);
    exports.boot = boot;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/vector/interrupt.js
var require_interrupt = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/vector/interrupt.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.nmi = exports.irq = exports.brk = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Interrupt = class {
      constructor(state, defaultVector, isBrk) {
        this.reset = () => this._result.read(this._dummyRead, this._state.p);
        this._dummyRead = () => {
          if (this._isBrk) {
            this._state.p = this._state.p + 1 & 65535;
          }
          return this._result.write(this._pushPch, 256 + this._state.s, this._state.p >>> 8);
        };
        this._pushPch = () => {
          this._state.s = this._state.s - 1 & 255;
          return this._result.write(this._pushPcl, 256 + this._state.s, this._state.p & 255).poll(true);
        };
        this._pushPcl = () => {
          this._state.s = this._state.s - 1 & 255;
          this._vector = this._state.nmi ? 65530 : this._defaultVector;
          return this._result.write(this._pushFlags, 256 + this._state.s, this._isBrk ? this._state.flags | 16 : this._state.flags & ~16);
        };
        this._pushFlags = () => {
          this._state.s = this._state.s - 1 & 255;
          return this._result.read(this._fetchPcl, this._vector);
        };
        this._fetchPcl = (value) => {
          this._state.flags |= 4;
          this._state.p = value;
          return this._result.read(this._fetchPch, ++this._vector);
        };
        this._fetchPch = (value) => {
          this._state.p = this._state.p | value << 8;
          this._state.nmi = this._state.irq = false;
          return null;
        };
        this._vector = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._defaultVector = defaultVector;
        this._isBrk = isBrk;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_dummyRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_pushPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_pushPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_pushFlags", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_fetchPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_fetchPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Interrupt.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Interrupt.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Number)
    ], Interrupt.prototype, "_defaultVector", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Boolean)
    ], Interrupt.prototype, "_isBrk", void 0);
    var brk = (state) => new Interrupt(state, 65534, true);
    exports.brk = brk;
    var irq = (state) => new Interrupt(state, 65534, false);
    exports.irq = irq;
    var nmi = (state) => new Interrupt(state, 65530, false);
    exports.nmi = nmi;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/vector/index.js
var require_vector = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/vector/index.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.irq = exports.nmi = exports.brk = exports.boot = void 0;
    var boot_1 = require_boot();
    Object.defineProperty(exports, "boot", { enumerable: true, get: function() {
      return boot_1.boot;
    } });
    var interrupt_1 = require_interrupt();
    Object.defineProperty(exports, "brk", { enumerable: true, get: function() {
      return interrupt_1.brk;
    } });
    Object.defineProperty(exports, "nmi", { enumerable: true, get: function() {
      return interrupt_1.nmi;
    } });
    Object.defineProperty(exports, "irq", { enumerable: true, get: function() {
      return interrupt_1.irq;
    } });
  }
});

// node_modules/6502.ts/lib/machine/cpu/Instruction.js
var require_Instruction = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/Instruction.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var Instruction = class {
      constructor(operation, addressingMode, effectiveAddressingMode = addressingMode) {
        this.operation = operation;
        this.addressingMode = addressingMode;
        this.effectiveAddressingMode = effectiveAddressingMode;
      }
      getSize() {
        switch (this.effectiveAddressingMode) {
          case 1:
          case 2:
          case 6:
          case 9:
          case 8:
          case 11:
          case 5:
            return 2;
          case 3:
          case 7:
          case 10:
          case 4:
            return 3;
          default:
            return 1;
        }
      }
    };
    exports.default = Instruction;
    (function(Instruction2) {
      let OperationMap;
      (function(OperationMap2) {
        OperationMap2[OperationMap2["adc"] = 0] = "adc";
        OperationMap2[OperationMap2["and"] = 1] = "and";
        OperationMap2[OperationMap2["asl"] = 2] = "asl";
        OperationMap2[OperationMap2["bcc"] = 3] = "bcc";
        OperationMap2[OperationMap2["bcs"] = 4] = "bcs";
        OperationMap2[OperationMap2["beq"] = 5] = "beq";
        OperationMap2[OperationMap2["bit"] = 6] = "bit";
        OperationMap2[OperationMap2["bmi"] = 7] = "bmi";
        OperationMap2[OperationMap2["bne"] = 8] = "bne";
        OperationMap2[OperationMap2["bpl"] = 9] = "bpl";
        OperationMap2[OperationMap2["brk"] = 10] = "brk";
        OperationMap2[OperationMap2["bvc"] = 11] = "bvc";
        OperationMap2[OperationMap2["bvs"] = 12] = "bvs";
        OperationMap2[OperationMap2["clc"] = 13] = "clc";
        OperationMap2[OperationMap2["cld"] = 14] = "cld";
        OperationMap2[OperationMap2["cli"] = 15] = "cli";
        OperationMap2[OperationMap2["clv"] = 16] = "clv";
        OperationMap2[OperationMap2["cmp"] = 17] = "cmp";
        OperationMap2[OperationMap2["cpx"] = 18] = "cpx";
        OperationMap2[OperationMap2["cpy"] = 19] = "cpy";
        OperationMap2[OperationMap2["dec"] = 20] = "dec";
        OperationMap2[OperationMap2["dex"] = 21] = "dex";
        OperationMap2[OperationMap2["dey"] = 22] = "dey";
        OperationMap2[OperationMap2["eor"] = 23] = "eor";
        OperationMap2[OperationMap2["inc"] = 24] = "inc";
        OperationMap2[OperationMap2["inx"] = 25] = "inx";
        OperationMap2[OperationMap2["iny"] = 26] = "iny";
        OperationMap2[OperationMap2["jmp"] = 27] = "jmp";
        OperationMap2[OperationMap2["jsr"] = 28] = "jsr";
        OperationMap2[OperationMap2["lda"] = 29] = "lda";
        OperationMap2[OperationMap2["ldx"] = 30] = "ldx";
        OperationMap2[OperationMap2["ldy"] = 31] = "ldy";
        OperationMap2[OperationMap2["lsr"] = 32] = "lsr";
        OperationMap2[OperationMap2["nop"] = 33] = "nop";
        OperationMap2[OperationMap2["ora"] = 34] = "ora";
        OperationMap2[OperationMap2["pha"] = 35] = "pha";
        OperationMap2[OperationMap2["php"] = 36] = "php";
        OperationMap2[OperationMap2["pla"] = 37] = "pla";
        OperationMap2[OperationMap2["plp"] = 38] = "plp";
        OperationMap2[OperationMap2["rol"] = 39] = "rol";
        OperationMap2[OperationMap2["ror"] = 40] = "ror";
        OperationMap2[OperationMap2["rti"] = 41] = "rti";
        OperationMap2[OperationMap2["rts"] = 42] = "rts";
        OperationMap2[OperationMap2["sbc"] = 43] = "sbc";
        OperationMap2[OperationMap2["sec"] = 44] = "sec";
        OperationMap2[OperationMap2["sed"] = 45] = "sed";
        OperationMap2[OperationMap2["sei"] = 46] = "sei";
        OperationMap2[OperationMap2["sta"] = 47] = "sta";
        OperationMap2[OperationMap2["stx"] = 48] = "stx";
        OperationMap2[OperationMap2["sty"] = 49] = "sty";
        OperationMap2[OperationMap2["tax"] = 50] = "tax";
        OperationMap2[OperationMap2["tay"] = 51] = "tay";
        OperationMap2[OperationMap2["tsx"] = 52] = "tsx";
        OperationMap2[OperationMap2["txa"] = 53] = "txa";
        OperationMap2[OperationMap2["txs"] = 54] = "txs";
        OperationMap2[OperationMap2["tya"] = 55] = "tya";
        OperationMap2[OperationMap2["dop"] = 56] = "dop";
        OperationMap2[OperationMap2["top"] = 57] = "top";
        OperationMap2[OperationMap2["alr"] = 58] = "alr";
        OperationMap2[OperationMap2["axs"] = 59] = "axs";
        OperationMap2[OperationMap2["dcp"] = 60] = "dcp";
        OperationMap2[OperationMap2["lax"] = 61] = "lax";
        OperationMap2[OperationMap2["arr"] = 62] = "arr";
        OperationMap2[OperationMap2["slo"] = 63] = "slo";
        OperationMap2[OperationMap2["aax"] = 64] = "aax";
        OperationMap2[OperationMap2["lar"] = 65] = "lar";
        OperationMap2[OperationMap2["isc"] = 66] = "isc";
        OperationMap2[OperationMap2["aac"] = 67] = "aac";
        OperationMap2[OperationMap2["atx"] = 68] = "atx";
        OperationMap2[OperationMap2["rra"] = 69] = "rra";
        OperationMap2[OperationMap2["rla"] = 70] = "rla";
        OperationMap2[OperationMap2["invalid"] = 71] = "invalid";
      })(OperationMap = Instruction2.OperationMap || (Instruction2.OperationMap = {}));
      Instruction2.opcodes = new Array(256);
    })(Instruction || (Instruction = {}));
    exports.default = Instruction;
    (function(Instruction2) {
      let __init;
      (function(__init2) {
        for (let i = 0; i < 256; i++) {
          Instruction2.opcodes[i] = new Instruction2(71, 12);
        }
        let operation, addressingMode, opcode;
        for (let i = 0; i < 8; i++) {
          switch (i) {
            case 0:
              operation = 34;
              break;
            case 1:
              operation = 1;
              break;
            case 2:
              operation = 23;
              break;
            case 3:
              operation = 0;
              break;
            case 4:
              operation = 47;
              break;
            case 5:
              operation = 29;
              break;
            case 6:
              operation = 17;
              break;
            case 7:
              operation = 43;
              break;
          }
          for (let j = 0; j < 8; j++) {
            switch (j) {
              case 0:
                addressingMode = 8;
                break;
              case 1:
                addressingMode = 2;
                break;
              case 2:
                addressingMode = 1;
                break;
              case 3:
                addressingMode = 3;
                break;
              case 4:
                addressingMode = 11;
                break;
              case 5:
                addressingMode = 6;
                break;
              case 6:
                addressingMode = 10;
                break;
              case 7:
                addressingMode = 7;
                break;
            }
            if (operation === 47 && addressingMode === 1) {
              addressingMode = 12;
            }
            if (operation !== 71 && addressingMode !== 12) {
              opcode = i << 5 | j << 2 | 1;
              Instruction2.opcodes[opcode] = new Instruction2(operation, addressingMode);
            }
          }
        }
        function set(_opcode, _operation, _addressingMode, _effectiveAdressingMode) {
          if (Instruction2.opcodes[_opcode].operation !== 71) {
            throw new Error("entry for opcode " + _opcode + " already exists");
          }
          Instruction2.opcodes[_opcode] = new Instruction2(_operation, _addressingMode, _effectiveAdressingMode);
        }
        set(6, 2, 2);
        set(10, 2, 0);
        set(14, 2, 3);
        set(22, 2, 6);
        set(30, 2, 7);
        set(38, 39, 2);
        set(42, 39, 0);
        set(46, 39, 3);
        set(54, 39, 6);
        set(62, 39, 7);
        set(70, 32, 2);
        set(74, 32, 0);
        set(78, 32, 3);
        set(86, 32, 6);
        set(94, 32, 7);
        set(102, 40, 2);
        set(106, 40, 0);
        set(110, 40, 3);
        set(118, 40, 6);
        set(126, 40, 7);
        set(134, 48, 2);
        set(142, 48, 3);
        set(150, 48, 9);
        set(162, 30, 1);
        set(166, 30, 2);
        set(174, 30, 3);
        set(182, 30, 9);
        set(190, 30, 10);
        set(198, 20, 2);
        set(206, 20, 3);
        set(214, 20, 6);
        set(222, 20, 7);
        set(230, 24, 2);
        set(238, 24, 3);
        set(246, 24, 6);
        set(254, 24, 7);
        set(36, 6, 2);
        set(44, 6, 3);
        set(76, 27, 3);
        set(108, 27, 4);
        set(132, 49, 2);
        set(140, 49, 3);
        set(148, 49, 6);
        set(160, 31, 1);
        set(164, 31, 2);
        set(172, 31, 3);
        set(180, 31, 6);
        set(188, 31, 7);
        set(192, 19, 1);
        set(196, 19, 2);
        set(204, 19, 3);
        set(224, 18, 1);
        set(228, 18, 2);
        set(236, 18, 3);
        set(16, 9, 5);
        set(48, 7, 5);
        set(80, 11, 5);
        set(112, 12, 5);
        set(144, 3, 5);
        set(176, 4, 5);
        set(208, 8, 5);
        set(240, 5, 5);
        set(0, 10, 0);
        set(32, 28, 0, 3);
        set(64, 41, 0);
        set(96, 42, 0);
        set(8, 36, 0);
        set(40, 38, 0);
        set(72, 35, 0);
        set(104, 37, 0);
        set(136, 22, 0);
        set(168, 51, 0);
        set(200, 26, 0);
        set(232, 25, 0);
        set(24, 13, 0);
        set(56, 44, 0);
        set(88, 15, 0);
        set(120, 46, 0);
        set(152, 55, 0);
        set(184, 16, 0);
        set(216, 14, 0);
        set(248, 45, 0);
        set(138, 53, 0);
        set(154, 54, 0);
        set(170, 50, 0);
        set(186, 52, 0);
        set(202, 21, 0);
        set(234, 33, 0);
        set(26, 33, 0);
        set(58, 33, 0);
        set(90, 33, 0);
        set(122, 33, 0);
        set(218, 33, 0);
        set(250, 33, 0);
        set(4, 56, 2);
        set(20, 56, 6);
        set(52, 56, 6);
        set(68, 56, 2);
        set(84, 56, 6);
        set(100, 56, 2);
        set(116, 56, 6);
        set(128, 56, 1);
        set(130, 56, 1);
        set(137, 56, 1);
        set(194, 56, 1);
        set(212, 56, 6);
        set(226, 56, 1);
        set(244, 56, 6);
        set(12, 57, 3);
        set(28, 57, 7);
        set(60, 57, 7);
        set(92, 57, 7);
        set(124, 57, 7);
        set(220, 57, 7);
        set(252, 57, 7);
        set(235, 43, 1);
        set(75, 58, 1);
        set(203, 59, 1);
        set(199, 60, 2);
        set(215, 60, 6);
        set(207, 60, 3);
        set(223, 60, 7);
        set(219, 60, 10);
        set(195, 60, 8);
        set(211, 60, 11);
        set(167, 61, 2);
        set(183, 61, 9);
        set(175, 61, 3);
        set(191, 61, 10);
        set(163, 61, 8);
        set(179, 61, 11);
        set(107, 62, 1);
        set(7, 63, 2);
        set(23, 63, 6);
        set(15, 63, 3);
        set(31, 63, 7);
        set(27, 63, 10);
        set(3, 63, 8);
        set(19, 63, 11);
        set(135, 64, 2);
        set(151, 64, 9);
        set(131, 64, 8);
        set(143, 64, 3);
        set(187, 65, 10);
        set(231, 66, 2);
        set(247, 66, 6);
        set(239, 66, 3);
        set(255, 66, 7);
        set(251, 66, 10);
        set(227, 66, 8);
        set(243, 66, 11);
        set(11, 67, 1);
        set(43, 67, 1);
        set(171, 68, 1);
        set(103, 69, 2);
        set(119, 69, 6);
        set(111, 69, 3);
        set(127, 69, 7);
        set(123, 69, 10);
        set(99, 69, 8);
        set(115, 69, 11);
        set(39, 70, 2);
        set(55, 70, 6);
        set(47, 70, 3);
        set(63, 70, 7);
        set(59, 70, 10);
        set(35, 70, 8);
        set(51, 70, 11);
      })(__init = Instruction2.__init || (Instruction2.__init = {}));
    })(Instruction || (Instruction = {}));
    exports.default = Instruction;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/absolute.js
var require_absolute = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/absolute.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.absolute = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Absolute = class {
      constructor(state, next = () => null) {
        this.reset = () => this._result.read(this._fetchLo, this._state.p);
        this._fetchLo = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._fetchHi, this._state.p);
        };
        this._fetchHi = (value) => {
          this._operand |= value << 8;
          this._state.p = this._state.p + 1 & 65535;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Absolute.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Absolute.prototype, "_fetchLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Absolute.prototype, "_fetchHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Absolute.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Absolute.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Absolute.prototype, "_next", void 0);
    var absolute = (state, next) => new Absolute(state, next);
    exports.absolute = absolute;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/absoluteIndexed.js
var require_absoluteIndexed = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/absoluteIndexed.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.absoluteY = exports.absoluteX = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var AbsoluteIndexed = class _AbsoluteIndexed {
      constructor(state, indexExtractor, next = () => null, writeOp = false) {
        this.reset = () => this._result.read(this._fetchLo, this._state.p);
        this._fetchLo = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._fetchHi, this._state.p);
        };
        this._fetchHi = (value) => {
          this._operand |= value << 8;
          this._state.p = this._state.p + 1 & 65535;
          const index = this._indexExtractor(this._state);
          this._carry = (this._operand & 255) + index > 255;
          this._operand = this._operand & 65280 | this._operand + index & 255;
          return this._carry || this._writeOp ? this._result.read(this._dereferenceAndCarry, this._operand) : this._next(this._operand, this._state);
        };
        this._dereferenceAndCarry = (value) => {
          if (this._carry) {
            this._operand = this._operand + 256 & 65535;
          }
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._carry = false;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._indexExtractor = indexExtractor;
        this._next = next;
        this._writeOp = writeOp;
        (0, decorators_1.freezeImmutables)(this);
      }
      static absoluteX(state, next, writeOp) {
        return new _AbsoluteIndexed(state, (s) => s.x, next, writeOp);
      }
      static absoluteY(state, next, writeOp) {
        return new _AbsoluteIndexed(state, (s) => s.y, next, writeOp);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], AbsoluteIndexed.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], AbsoluteIndexed.prototype, "_fetchLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], AbsoluteIndexed.prototype, "_fetchHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], AbsoluteIndexed.prototype, "_dereferenceAndCarry", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], AbsoluteIndexed.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], AbsoluteIndexed.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], AbsoluteIndexed.prototype, "_indexExtractor", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], AbsoluteIndexed.prototype, "_next", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Boolean)
    ], AbsoluteIndexed.prototype, "_writeOp", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function),
      tslib_1.__metadata("design:paramtypes", [CpuInterface_1.default.State, Function, Boolean]),
      tslib_1.__metadata("design:returntype", AbsoluteIndexed)
    ], AbsoluteIndexed, "absoluteX", null);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function),
      tslib_1.__metadata("design:paramtypes", [CpuInterface_1.default.State, Function, Boolean]),
      tslib_1.__metadata("design:returntype", AbsoluteIndexed)
    ], AbsoluteIndexed, "absoluteY", null);
    var absoluteX = (state, next, writeOp) => AbsoluteIndexed.absoluteX(state, next, writeOp);
    exports.absoluteX = absoluteX;
    var absoluteY = (state, next, writeOp) => AbsoluteIndexed.absoluteY(state, next, writeOp);
    exports.absoluteY = absoluteY;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/dereference.js
var require_dereference = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/dereference.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.dereference = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var Dereference = class {
      constructor(state, next = () => null) {
        this.reset = (operand) => this._result.read(this._dereference, operand);
        this._dereference = (value) => this._next(value, this._state);
        this._result = new ResultImpl_1.default();
        this._next = next;
        this._state = state;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Dereference.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Dereference.prototype, "_dereference", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Dereference.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Dereference.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Dereference.prototype, "_next", void 0);
    var dereference = (state, next) => new Dereference(state, next);
    exports.dereference = dereference;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/immediate.js
var require_immediate = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/immediate.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.immediate = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Immediate = class {
      constructor(state, next = () => null) {
        this.reset = () => this._result.read(this._fetchOperand, this._state.p);
        this._fetchOperand = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Immediate.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Immediate.prototype, "_fetchOperand", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Immediate.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Immediate.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Immediate.prototype, "_next", void 0);
    var immediate = (state, next) => new Immediate(state, next);
    exports.immediate = immediate;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indexedIndirectX.js
var require_indexedIndirectX = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indexedIndirectX.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.indexedIndirectX = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var IndexedIndirectX = class {
      constructor(state, next = () => null) {
        this.reset = () => this._result.read(this._fetchAddress, this._state.p);
        this._fetchAddress = (value) => {
          this._address = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._addIndex, this._address);
        };
        this._addIndex = (value) => {
          this._address = this._address + this._state.x & 255;
          return this._result.read(this._fetchLo, this._address);
        };
        this._fetchLo = (value) => {
          this._operand = value;
          this._address = this._address + 1 & 255;
          return this._result.read(this._fetchHi, this._address);
        };
        this._fetchHi = (value) => {
          this._operand |= value << 8;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._address = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "_fetchAddress", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "_addIndex", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "_fetchLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "_fetchHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectX.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], IndexedIndirectX.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], IndexedIndirectX.prototype, "_next", void 0);
    var indexedIndirectX = (state, next) => new IndexedIndirectX(state, next);
    exports.indexedIndirectX = indexedIndirectX;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indirectIndexedY.js
var require_indirectIndexedY = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indirectIndexedY.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.indirectIndexedY = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var IndexedIndirectY = class {
      constructor(state, next = () => null, writeOp) {
        this.reset = () => this._result.read(this._fetchAddress, this._state.p);
        this._fetchAddress = (value) => {
          this._address = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._fetchLo, this._address);
        };
        this._fetchLo = (value) => {
          this._operand = value;
          this._address = this._address + 1 & 255;
          return this._result.read(this._fetchHi, this._address);
        };
        this._fetchHi = (value) => {
          this._operand |= value << 8;
          this._carry = (this._operand & 255) + this._state.y > 255;
          this._operand = this._operand & 65280 | this._operand + this._state.y & 255;
          return this._carry || this._writeOp ? this._result.read(this._dereferenceAndCarry, this._operand) : this._next(this._operand, this._state);
        };
        this._dereferenceAndCarry = (value) => {
          if (this._carry) {
            this._operand = this._operand + 256 & 65535;
          }
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._address = 0;
        this._carry = false;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        this._writeOp = writeOp;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "_fetchAddress", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "_fetchLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "_fetchHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "_dereferenceAndCarry", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], IndexedIndirectY.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], IndexedIndirectY.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], IndexedIndirectY.prototype, "_next", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Boolean)
    ], IndexedIndirectY.prototype, "_writeOp", void 0);
    var indirectIndexedY = (state, next, writeOp) => new IndexedIndirectY(state, next, writeOp);
    exports.indirectIndexedY = indirectIndexedY;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/zeroPage.js
var require_zeroPage = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/zeroPage.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.zeroPage = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var ZeroPage = class {
      constructor(state, next = () => null) {
        this.reset = () => this._result.read(this._fetchAddress, this._state.p);
        this._fetchAddress = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPage.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPage.prototype, "_fetchAddress", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPage.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], ZeroPage.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], ZeroPage.prototype, "_next", void 0);
    var zeroPage = (state, next) => new ZeroPage(state, next);
    exports.zeroPage = zeroPage;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/zeroPageIndexed.js
var require_zeroPageIndexed = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/zeroPageIndexed.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.zeroPageY = exports.zeroPageX = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var ZeroPageIndexed = class _ZeroPageIndexed {
      constructor(state, indexExtractor, next) {
        this.reset = () => this._result.read(this._fetchAddress, this._state.p);
        this._fetchAddress = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._addIndex, this._operand);
        };
        this._addIndex = (value) => {
          this._operand = this._operand + this._indexExtractor(this._state) & 255;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._indexExtractor = indexExtractor;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
      static zeroPageX(state, next = () => null) {
        return new _ZeroPageIndexed(state, (s) => s.x, next);
      }
      static zeroPageY(state, next = () => null) {
        return new _ZeroPageIndexed(state, (s) => s.y, next);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPageIndexed.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPageIndexed.prototype, "_fetchAddress", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPageIndexed.prototype, "_addIndex", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ZeroPageIndexed.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], ZeroPageIndexed.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], ZeroPageIndexed.prototype, "_next", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], ZeroPageIndexed.prototype, "_indexExtractor", void 0);
    var zeroPageX = (state, next) => ZeroPageIndexed.zeroPageX(state, next);
    exports.zeroPageX = zeroPageX;
    var zeroPageY = (state, next) => ZeroPageIndexed.zeroPageY(state, next);
    exports.zeroPageY = zeroPageY;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/index.js
var require_addressing = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/index.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.zeroPageY = exports.zeroPageX = exports.zeroPage = exports.indirectIndexedY = exports.indexedIndirectX = exports.immediate = exports.dereference = exports.absoluteY = exports.absoluteX = exports.absolute = void 0;
    var absolute_1 = require_absolute();
    Object.defineProperty(exports, "absolute", { enumerable: true, get: function() {
      return absolute_1.absolute;
    } });
    var absoluteIndexed_1 = require_absoluteIndexed();
    Object.defineProperty(exports, "absoluteX", { enumerable: true, get: function() {
      return absoluteIndexed_1.absoluteX;
    } });
    Object.defineProperty(exports, "absoluteY", { enumerable: true, get: function() {
      return absoluteIndexed_1.absoluteY;
    } });
    var dereference_1 = require_dereference();
    Object.defineProperty(exports, "dereference", { enumerable: true, get: function() {
      return dereference_1.dereference;
    } });
    var immediate_1 = require_immediate();
    Object.defineProperty(exports, "immediate", { enumerable: true, get: function() {
      return immediate_1.immediate;
    } });
    var indexedIndirectX_1 = require_indexedIndirectX();
    Object.defineProperty(exports, "indexedIndirectX", { enumerable: true, get: function() {
      return indexedIndirectX_1.indexedIndirectX;
    } });
    var indirectIndexedY_1 = require_indirectIndexedY();
    Object.defineProperty(exports, "indirectIndexedY", { enumerable: true, get: function() {
      return indirectIndexedY_1.indirectIndexedY;
    } });
    var zeroPage_1 = require_zeroPage();
    Object.defineProperty(exports, "zeroPage", { enumerable: true, get: function() {
      return zeroPage_1.zeroPage;
    } });
    var zeroPageIndexed_1 = require_zeroPageIndexed();
    Object.defineProperty(exports, "zeroPageX", { enumerable: true, get: function() {
      return zeroPageIndexed_1.zeroPageX;
    } });
    Object.defineProperty(exports, "zeroPageY", { enumerable: true, get: function() {
      return zeroPageIndexed_1.zeroPageY;
    } });
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/branch.js
var require_branch = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/branch.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.branch = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Branch = class {
      constructor(state, predicate) {
        this.reset = () => this._result.read(this._fetchTarget, this._state.p).poll(true);
        this._fetchTarget = (value) => {
          this._operand = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._predicate(this._state.flags) ? this._result.read(this._firstDummyRead, this._state.p) : null;
        };
        this._firstDummyRead = (value) => {
          this._target = this._state.p + (this._operand & 128 ? this._operand - 256 : this._operand) & 65535;
          if ((this._target & 65280) === (this._state.p & 65280)) {
            this._state.p = this._target;
            return null;
          }
          return this._result.read(this._secondDummyRead, this._state.p & 65280 | this._target & 255).poll(true);
        };
        this._secondDummyRead = (value) => {
          this._state.p = this._target;
          return null;
        };
        this._target = 0;
        this._operand = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._predicate = predicate;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Branch.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Branch.prototype, "_fetchTarget", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Branch.prototype, "_firstDummyRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Branch.prototype, "_secondDummyRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Branch.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Branch.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Branch.prototype, "_predicate", void 0);
    var branch = (state, predicate) => new Branch(state, predicate);
    exports.branch = branch;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/jsr.js
var require_jsr = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/jsr.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.jsr = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Jsr = class {
      constructor(state) {
        this.reset = () => this._result.read(this._fetchPcl, this._state.p);
        this._fetchPcl = (value) => {
          this._addressLo = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._dummyStackRead, 256 + this._state.s);
        };
        this._dummyStackRead = () => this._result.write(this._pushPch, 256 + this._state.s, this._state.p >>> 8);
        this._pushPch = () => {
          this._state.s = this._state.s - 1 & 255;
          return this._result.write(this._pushPcl, 256 + this._state.s, this._state.p & 255);
        };
        this._pushPcl = () => {
          this._state.s = this._state.s - 1 & 255;
          return this._result.read(this._fetchPch, this._state.p);
        };
        this._fetchPch = (value) => {
          this._state.p = this._addressLo | value << 8;
          return null;
        };
        this._addressLo = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_fetchPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_dummyStackRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_pushPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_pushPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_fetchPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Jsr.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Jsr.prototype, "_state", void 0);
    var jsr = (state) => new Jsr(state);
    exports.jsr = jsr;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/readModifyWrite.js
var require_readModifyWrite = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/readModifyWrite.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.readModifyWrite = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var ReadModifyWrite = class {
      constructor(state, operation) {
        this.reset = (address) => {
          this._address = address;
          return this._result.read(this._read, address);
        };
        this._read = (value) => {
          this._operand = value;
          return this._result.write(this._dummyWrite, this._address, this._operand);
        };
        this._dummyWrite = (value) => this._result.write(this._write, this._address, this._operation(this._operand, this._state));
        this._write = () => null;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._operation = operation;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ReadModifyWrite.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ReadModifyWrite.prototype, "_read", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ReadModifyWrite.prototype, "_dummyWrite", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ReadModifyWrite.prototype, "_write", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], ReadModifyWrite.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], ReadModifyWrite.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], ReadModifyWrite.prototype, "_operation", void 0);
    var readModifyWrite = (state, operation) => new ReadModifyWrite(state, operation);
    exports.readModifyWrite = readModifyWrite;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/rts.js
var require_rts = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/rts.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.rts = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Rts = class {
      constructor(state) {
        this.reset = () => this._result.read(this._dummyOperandRead, this._state.p);
        this._dummyOperandRead = () => this._result.read(this._dummyStackRead, 256 + this._state.s);
        this._dummyStackRead = () => {
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._popPcl, 256 + this._state.s);
        };
        this._popPcl = (value) => {
          this._state.p = this._state.p & 65280 | value;
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._popPch, 256 + this._state.s);
        };
        this._popPch = (value) => {
          this._state.p = this._state.p & 255 | value << 8;
          return this._result.read(this._incrementP, this._state.p);
        };
        this._incrementP = () => {
          this._state.p = this._state.p + 1 & 65535;
          return null;
        };
        this._result = new ResultImpl_1.default();
        this._state = state;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_dummyOperandRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_dummyStackRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_popPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_popPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_incrementP", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rts.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Rts.prototype, "_state", void 0);
    var rts = (state) => new Rts(state);
    exports.rts = rts;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/nullaryOneCycle.js
var require_nullaryOneCycle = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/nullaryOneCycle.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.nullaryOneCycle = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var NullaryOneCycle = class {
      constructor(state, operation) {
        this.reset = () => this._result.read(this._executeOperation, this._state.p).poll(true);
        this._executeOperation = () => {
          this._operation(this._state);
          return null;
        };
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._operation = operation;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], NullaryOneCycle.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], NullaryOneCycle.prototype, "_executeOperation", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], NullaryOneCycle.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], NullaryOneCycle.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], NullaryOneCycle.prototype, "_operation", void 0);
    var nullaryOneCycle = (state, operation) => new NullaryOneCycle(state, operation);
    exports.nullaryOneCycle = nullaryOneCycle;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/pull.js
var require_pull = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/pull.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.pull = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var decorators_1 = require_decorators();
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var Pull = class {
      constructor(state, operation) {
        this.reset = () => this._result.read(this._dummyRead, this._state.p).poll(true);
        this._dummyRead = () => this._result.read(this._incrementS, 256 + this._state.s);
        this._incrementS = () => {
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._pull, 256 + this._state.s);
        };
        this._pull = (value) => (this._operation(this._state, value), null);
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._operation = operation;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Pull.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Pull.prototype, "_dummyRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Pull.prototype, "_incrementS", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Pull.prototype, "_pull", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Pull.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Pull.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Pull.prototype, "_operation", void 0);
    var pull = (state, operation) => new Pull(state, operation);
    exports.pull = pull;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/push.js
var require_push = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/push.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.push = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var decorators_1 = require_decorators();
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var Push = class {
      constructor(state, operation) {
        this.reset = () => this._result.read(this._dummyRead, this._state.p);
        this._dummyRead = () => this._result.write(this._push, 256 + this._state.s, this._operation(this._state));
        this._push = () => {
          this._state.s = this._state.s - 1 & 255;
          return null;
        };
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._operation = operation;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Push.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Push.prototype, "_dummyRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Push.prototype, "_push", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Push.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Push.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Push.prototype, "_operation", void 0);
    var push = (state, operation) => new Push(state, operation);
    exports.push = push;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/rti.js
var require_rti = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/rti.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.rti = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Rti = class {
      constructor(state) {
        this.reset = () => this._result.read(this._dummyOperandRead, this._state.p);
        this._dummyOperandRead = () => this._result.read(this._dummyStackRead, 256 + this._state.s);
        this._dummyStackRead = () => {
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._popP, 256 + this._state.s);
        };
        this._popP = (value) => {
          this._state.flags = (value | 32) & ~16;
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._popPcl, 256 + this._state.s);
        };
        this._popPcl = (value) => {
          this._state.p = this._state.p & 65280 | value;
          this._state.s = this._state.s + 1 & 255;
          return this._result.read(this._popPch, 256 + this._state.s);
        };
        this._popPch = (value) => {
          this._state.p = this._state.p & 255 | value << 8;
          return null;
        };
        this._result = new ResultImpl_1.default();
        this._state = state;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_dummyOperandRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_dummyStackRead", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_popP", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_popPcl", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_popPch", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Rti.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Rti.prototype, "_state", void 0);
    var rti = (state) => new Rti(state);
    exports.rti = rti;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/write.js
var require_write = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/write.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.write = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Write = class {
      constructor(state, operation) {
        this.reset = (operand) => this._result.write(() => null, operand, this._operation(this._state));
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._operation = operation;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Write.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Write.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Write.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Write.prototype, "_operation", void 0);
    var write = (state, operation) => new Write(state, operation);
    exports.write = write;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/index.js
var require_instruction = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/instruction/index.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.write = exports.rti = exports.push = exports.pull = exports.nullaryOneCycle = exports.rts = exports.readModifyWrite = exports.jsr = exports.branch = void 0;
    var branch_1 = require_branch();
    Object.defineProperty(exports, "branch", { enumerable: true, get: function() {
      return branch_1.branch;
    } });
    var jsr_1 = require_jsr();
    Object.defineProperty(exports, "jsr", { enumerable: true, get: function() {
      return jsr_1.jsr;
    } });
    var readModifyWrite_1 = require_readModifyWrite();
    Object.defineProperty(exports, "readModifyWrite", { enumerable: true, get: function() {
      return readModifyWrite_1.readModifyWrite;
    } });
    var rts_1 = require_rts();
    Object.defineProperty(exports, "rts", { enumerable: true, get: function() {
      return rts_1.rts;
    } });
    var nullaryOneCycle_1 = require_nullaryOneCycle();
    Object.defineProperty(exports, "nullaryOneCycle", { enumerable: true, get: function() {
      return nullaryOneCycle_1.nullaryOneCycle;
    } });
    var pull_1 = require_pull();
    Object.defineProperty(exports, "pull", { enumerable: true, get: function() {
      return pull_1.pull;
    } });
    var push_1 = require_push();
    Object.defineProperty(exports, "push", { enumerable: true, get: function() {
      return push_1.push;
    } });
    var rti_1 = require_rti();
    Object.defineProperty(exports, "rti", { enumerable: true, get: function() {
      return rti_1.rti;
    } });
    var write_1 = require_write();
    Object.defineProperty(exports, "write", { enumerable: true, get: function() {
      return write_1.write;
    } });
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/ops.js
var require_ops = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/ops.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.aac = exports.isc = exports.aax = exports.slo = exports.rla = exports.rra = exports.axs = exports.dcp = exports.alr = exports.arr = exports.rorRmw = exports.rorImmediate = exports.rolRmw = exports.rolImmediate = exports.lsrRmw = exports.lsrImmediate = exports.sbc = exports.cmp = exports.bit = exports.aslRmw = exports.aslImmediate = exports.adc = exports.genUnary = exports.genNullary = exports.genRmw = void 0;
    function setFlagsNZ(operand, state) {
      state.flags = state.flags & ~(128 | 2) | operand & 128 | (operand ? 0 : 2);
    }
    function genRmw(operand, state, operation) {
      const result = operation(operand);
      setFlagsNZ(result, state);
      return result;
    }
    exports.genRmw = genRmw;
    function genNullary(state, operation) {
      setFlagsNZ(operation(state), state);
    }
    exports.genNullary = genNullary;
    function genUnary(operand, state, operation) {
      setFlagsNZ(operation(operand, state), state);
      return null;
    }
    exports.genUnary = genUnary;
    function adc(operand, state) {
      if (state.flags & 8) {
        const d0 = (operand & 15) + (state.a & 15) + (state.flags & 1), d1 = (operand >>> 4) + (state.a >>> 4) + (d0 > 9 ? 1 : 0);
        state.a = d0 % 10 | d1 % 10 << 4;
        state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | (d1 > 9 ? 1 : 0);
      } else {
        const sum = state.a + operand + (state.flags & 1), result = sum & 255;
        state.flags = state.flags & ~(128 | 2 | 1 | 64) | result & 128 | (result ? 0 : 2) | sum >>> 8 | (~(operand ^ state.a) & (result ^ operand) & 128) >>> 1;
        state.a = result;
      }
      return null;
    }
    exports.adc = adc;
    function aslImmediate(state) {
      const old = state.a;
      state.a = state.a << 1 & 255;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old >>> 7;
    }
    exports.aslImmediate = aslImmediate;
    function aslRmw(operand, state) {
      const result = operand << 1 & 255;
      state.flags = state.flags & ~(128 | 2 | 1) | result & 128 | (result ? 0 : 2) | operand >>> 7;
      return result;
    }
    exports.aslRmw = aslRmw;
    function bit(operand, state) {
      state.flags = state.flags & ~(128 | 64 | 2) | operand & (128 | 64) | (operand & state.a ? 0 : 2);
      return null;
    }
    exports.bit = bit;
    function cmp(operand, state, getRegister) {
      const diff = getRegister(state) + (~operand & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
    }
    exports.cmp = cmp;
    function sbc(operand, state) {
      if (state.flags & 8) {
        const d0 = (state.a & 15) - (operand & 15) - (~state.flags & 1), d1 = (state.a >>> 4) - (operand >>> 4) - (d0 < 0 ? 1 : 0);
        state.a = (d0 < 0 ? 10 + d0 : d0) | (d1 < 0 ? 10 + d1 : d1) << 4;
        state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | (d1 < 0 ? 0 : 1);
      } else {
        operand = ~operand & 255;
        const sum = state.a + operand + (state.flags & 1), result = sum & 255;
        state.flags = state.flags & ~(128 | 2 | 1 | 64) | result & 128 | (result ? 0 : 2) | sum >>> 8 | (~(operand ^ state.a) & (result ^ operand) & 128) >>> 1;
        state.a = result;
      }
      return null;
    }
    exports.sbc = sbc;
    function lsrImmediate(state) {
      const old = state.a;
      state.a = state.a >>> 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old & 1;
    }
    exports.lsrImmediate = lsrImmediate;
    function lsrRmw(operand, state) {
      const result = operand >>> 1;
      state.flags = state.flags & ~(128 | 2 | 1) | result & 128 | (result ? 0 : 2) | operand & 1;
      return result;
    }
    exports.lsrRmw = lsrRmw;
    function rolImmediate(state) {
      const old = state.a;
      state.a = state.a << 1 & 255 | state.flags & 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old >>> 7;
    }
    exports.rolImmediate = rolImmediate;
    function rolRmw(operand, state) {
      const result = operand << 1 & 255 | state.flags & 1;
      state.flags = state.flags & ~(128 | 2 | 1) | result & 128 | (result ? 0 : 2) | operand >>> 7;
      return result;
    }
    exports.rolRmw = rolRmw;
    function rorImmediate(state) {
      const old = state.a;
      state.a = state.a >>> 1 | (state.flags & 1) << 7;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old & 1;
    }
    exports.rorImmediate = rorImmediate;
    function rorRmw(operand, state) {
      const result = operand >>> 1 | (state.flags & 1) << 7;
      state.flags = state.flags & ~(128 | 2 | 1) | result & 128 | (result ? 0 : 2) | operand & 1;
      return result;
    }
    exports.rorRmw = rorRmw;
    function arr(operand, state) {
      state.a = (state.a & operand) >>> 1 | (state.flags & 1 ? 128 : 0);
      state.flags = state.flags & ~(1 | 128 | 2 | 64) | (state.a & 64) >>> 6 | (state.a ? 0 : 2) | state.a & 128 | state.a & 64 ^ (state.a & 32) << 1;
    }
    exports.arr = arr;
    function alr(operand, state) {
      const i = state.a & operand;
      state.a = i >>> 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | i & 1;
      return null;
    }
    exports.alr = alr;
    function dcp(operand, state) {
      const result = operand + 255 & 255;
      const diff = state.a + (~result & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
      return result;
    }
    exports.dcp = dcp;
    function axs(operand, state) {
      const value = (state.a & state.x) + (~operand & 255) + 1;
      state.x = value & 255;
      state.flags = state.flags & ~(128 | 2 | 1) | state.x & 128 | (state.x & 255 ? 0 : 2) | value >>> 8;
      return null;
    }
    exports.axs = axs;
    function rra(operand, state) {
      const result = operand >>> 1 | (state.flags & 1) << 7;
      state.flags = state.flags & ~1 | operand & 1;
      adc(result, state);
      return result;
    }
    exports.rra = rra;
    function rla(operand, state) {
      const result = operand << 1 & 255 | state.flags & 1;
      state.flags = state.flags & ~1 | operand >>> 7;
      setFlagsNZ(state.a &= result, state);
      return result;
    }
    exports.rla = rla;
    function slo(operand, state) {
      state.flags = state.flags & ~1 | operand >>> 7;
      const result = operand << 1 & 255;
      state.a = state.a | result;
      setFlagsNZ(state.a, state);
      return result;
    }
    exports.slo = slo;
    function aax(state) {
      const result = state.a & state.x;
      setFlagsNZ(result, state);
      return result;
    }
    exports.aax = aax;
    function isc(operand, state) {
      const result = operand + 1 & 255;
      sbc(result, state);
      return result;
    }
    exports.isc = isc;
    function aac(operand, state) {
      state.a &= operand;
      setFlagsNZ(state.a, state);
      state.flags = state.flags & ~1 | (state.a & 128) >>> 7;
      return null;
    }
    exports.aac = aac;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indirect.js
var require_indirect = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/addressing/indirect.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.indirect = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ResultImpl_1 = tslib_1.__importDefault(require_ResultImpl());
    var decorators_1 = require_decorators();
    var Indirect = class {
      constructor(state, next = () => null) {
        this.reset = () => this._result.read(this._fetchAddressLo, this._state.p);
        this._fetchAddressLo = (value) => {
          this._address = value;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._fetchAddressHi, this._state.p);
        };
        this._fetchAddressHi = (value) => {
          this._address |= value << 8;
          this._state.p = this._state.p + 1 & 65535;
          return this._result.read(this._fetchLo, this._address);
        };
        this._fetchLo = (value) => {
          this._operand = value;
          if ((this._address & 255) === 255) {
            this._address &= 65280;
          } else {
            this._address = this._address + 1 & 65535;
          }
          return this._result.read(this._fetchHi, this._address);
        };
        this._fetchHi = (value) => {
          this._operand |= value << 8;
          return this._next(this._operand, this._state);
        };
        this._operand = 0;
        this._address = 0;
        this._result = new ResultImpl_1.default();
        this._state = state;
        this._next = next;
        (0, decorators_1.freezeImmutables)(this);
      }
    };
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "reset", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "_fetchAddressLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "_fetchAddressHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "_fetchLo", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "_fetchHi", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Object)
    ], Indirect.prototype, "_result", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", CpuInterface_1.default.State)
    ], Indirect.prototype, "_state", void 0);
    tslib_1.__decorate([
      decorators_1.Immutable,
      tslib_1.__metadata("design:type", Function)
    ], Indirect.prototype, "_next", void 0);
    var indirect = (state, next) => new Indirect(state, next);
    exports.indirect = indirect;
  }
});

// node_modules/6502.ts/lib/machine/cpu/statemachine/Compiler.js
var require_Compiler = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/statemachine/Compiler.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Instruction_1 = tslib_1.__importDefault(require_Instruction());
    var addressing_1 = require_addressing();
    var instruction_1 = require_instruction();
    var ops = tslib_1.__importStar(require_ops());
    var indirect_1 = require_indirect();
    var vector_1 = require_vector();
    var Compiler = class {
      constructor(_state) {
        this._state = _state;
      }
      compile(op) {
        const instruction = Instruction_1.default.opcodes[op];
        switch (instruction.operation) {
          case 0:
            return this._createAddressing(instruction.addressingMode, ops.adc, {
              deref: true
            });
          case 1:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.a = state.a & operand), {
              deref: true
            });
          case 2:
            return instruction.addressingMode === 0 ? (0, instruction_1.nullaryOneCycle)(this._state, ops.aslImmediate) : this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.aslRmw).reset, { writeOp: true });
          case 6:
            return this._createAddressing(instruction.addressingMode, ops.bit, {
              deref: true
            });
          case 10:
            return (0, vector_1.brk)(this._state);
          case 17:
            return this._createAddressing(instruction.addressingMode, (o, s) => (ops.cmp(o, s, (state) => state.a), null), {
              deref: true
            });
          case 18:
            return this._createAddressing(instruction.addressingMode, (o, s) => (ops.cmp(o, s, (state) => state.x), null), {
              deref: true
            });
          case 19:
            return this._createAddressing(instruction.addressingMode, (o, s) => (ops.cmp(o, s, (state) => state.y), null), {
              deref: true
            });
          case 20:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, (s, o) => ops.genRmw(s, o, (x) => x - 1 & 255)).reset, {
              writeOp: true
            });
          case 21:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.x = state.x - 1 & 255));
          case 22:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.y = state.y - 1 & 255));
          case 24:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, (s, o) => ops.genRmw(s, o, (x) => x + 1 & 255)).reset, {
              writeOp: true
            });
          case 25:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.x = state.x + 1 & 255));
          case 26:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.y = state.y + 1 & 255));
          case 23:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.a = state.a ^ operand), {
              deref: true
            });
          case 27:
            return this._createAddressing(instruction.addressingMode, (o, s) => (s.p = o, null));
          case 28:
            return (0, instruction_1.jsr)(this._state);
          case 29:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.a = operand), {
              deref: true
            });
          case 30:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.x = operand), {
              deref: true
            });
          case 31:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.y = operand), {
              deref: true
            });
          case 32:
            return instruction.addressingMode === 0 ? (0, instruction_1.nullaryOneCycle)(this._state, ops.lsrImmediate) : this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.lsrRmw).reset, { writeOp: true });
          case 33:
            return (0, instruction_1.nullaryOneCycle)(this._state, () => void 0);
          case 34:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.a |= operand), { deref: true });
          case 35:
            return (0, instruction_1.push)(this._state, (s) => s.a);
          case 36:
            return (0, instruction_1.push)(this._state, (s) => s.flags | 16);
          case 37:
            return (0, instruction_1.pull)(this._state, (s, o) => ops.genNullary(s, (state) => state.a = o));
          case 38:
            return (0, instruction_1.pull)(this._state, (s, o) => s.flags = (o | 32) & ~16);
          case 39:
            return instruction.addressingMode === 0 ? (0, instruction_1.nullaryOneCycle)(this._state, ops.rolImmediate) : this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.rolRmw).reset, { writeOp: true });
          case 40:
            return instruction.addressingMode === 0 ? (0, instruction_1.nullaryOneCycle)(this._state, ops.rorImmediate) : this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.rorRmw).reset, { writeOp: true });
          case 41:
            return (0, instruction_1.rti)(this._state);
          case 42:
            return (0, instruction_1.rts)(this._state);
          case 43:
            return this._createAddressing(instruction.addressingMode, ops.sbc, {
              deref: true
            });
          case 48:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.write)(this._state, (s) => s.x).reset, {
              writeOp: true
            });
          case 49:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.write)(this._state, (s) => s.y).reset, {
              writeOp: true
            });
          case 50:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.x = state.a));
          case 51:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.y = state.a));
          case 52:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.x = state.s));
          case 53:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.a = state.x));
          case 54:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.s = s.x);
          case 55:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => ops.genNullary(s, (state) => state.a = state.y));
          case 3:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 1) === 0);
          case 4:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 1) > 0);
          case 8:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 2) === 0);
          case 5:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 2) > 0);
          case 9:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 128) === 0);
          case 7:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 128) > 0);
          case 11:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 64) === 0);
          case 12:
            return (0, instruction_1.branch)(this._state, (flags) => (flags & 64) > 0);
          case 44:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags |= 1);
          case 45:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags |= 8);
          case 46:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags |= 4);
          case 47:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.write)(this._state, (s) => s.a).reset, {
              writeOp: true
            });
          case 13:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags &= ~1);
          case 14:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags &= ~8);
          case 15:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags &= ~4);
          case 16:
            return (0, instruction_1.nullaryOneCycle)(this._state, (s) => s.flags &= ~64);
          case 56:
          case 57:
            return this._createAddressing(instruction.addressingMode, () => null, { deref: true });
          case 67:
            return this._createAddressing(instruction.addressingMode, ops.aac);
          case 64:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.write)(this._state, ops.aax).reset, {
              writeOp: true
            });
          case 58:
            return this._createAddressing(instruction.addressingMode, ops.alr, {
              deref: true
            });
          case 62:
            return this._createAddressing(instruction.addressingMode, (o, s) => (ops.arr(o, s), null), {
              deref: true
            });
          case 59:
            return this._createAddressing(instruction.addressingMode, ops.axs, {
              deref: true
            });
          case 68:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.x = state.a = state.a & operand), {
              deref: true
            });
          case 60:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.dcp).reset, {
              writeOp: true
            });
          case 66:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.isc).reset, {
              writeOp: true
            });
          case 61:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.a = state.x = operand), {
              deref: true
            });
          case 65:
            return this._createAddressing(instruction.addressingMode, (o, s) => ops.genUnary(o, s, (operand, state) => state.s = state.x = state.a = state.s & operand), { deref: true });
          case 70:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.rla).reset, {
              writeOp: true
            });
          case 69:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.rra).reset, {
              writeOp: true
            });
          case 63:
            return this._createAddressing(instruction.addressingMode, (0, instruction_1.readModifyWrite)(this._state, ops.slo).reset, {
              writeOp: true
            });
          default:
            return null;
        }
      }
      _createAddressing(addressingMode, next, { deref = false, writeOp = false } = {}) {
        if (deref && addressingMode !== 1) {
          next = (0, addressing_1.dereference)(this._state, next).reset;
        }
        switch (addressingMode) {
          case 1:
            return (0, addressing_1.immediate)(this._state, next);
          case 2:
            return (0, addressing_1.zeroPage)(this._state, next);
          case 3:
            return (0, addressing_1.absolute)(this._state, next);
          case 6:
            return (0, addressing_1.zeroPageX)(this._state, next);
          case 9:
            return (0, addressing_1.zeroPageY)(this._state, next);
          case 7:
            return (0, addressing_1.absoluteX)(this._state, next, writeOp);
          case 10:
            return (0, addressing_1.absoluteY)(this._state, next, writeOp);
          case 8:
            return (0, addressing_1.indexedIndirectX)(this._state, next);
          case 11:
            return (0, addressing_1.indirectIndexedY)(this._state, next, writeOp);
          case 4:
            return (0, indirect_1.indirect)(this._state, next);
          default:
            throw new Error(`invalid addressing mode ${addressingMode}`);
        }
      }
    };
    exports.default = Compiler;
  }
});

// node_modules/6502.ts/lib/machine/cpu/StateMachineCpu.js
var require_StateMachineCpu = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/StateMachineCpu.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var vector_1 = require_vector();
    var Compiler_1 = tslib_1.__importDefault(require_Compiler());
    var StateMachineCpu = class {
      constructor(_bus, _rng) {
        this._bus = _bus;
        this._rng = _rng;
        this.executionState = 0;
        this.state = new CpuInterface_1.default.State();
        this._invalidInstructionCallback = null;
        this._interruptPending = false;
        this._nmiPending = false;
        this._halt = false;
        this._pollInterruptsAfterLastInstruction = false;
        this._lastInstructionPointer = 0;
        this._operations = new Array(255);
        this._opBoot = (0, vector_1.boot)(this.state);
        this._opIrq = (0, vector_1.irq)(this.state);
        this._opNmi = (0, vector_1.nmi)(this.state);
        const compiler = new Compiler_1.default(this.state);
        for (let op = 0; op < 256; op++) {
          this._operations[op] = compiler.compile(op);
        }
        this.reset();
      }
      reset() {
        this.state.a = this._rng ? this._rng.int(255) : 0;
        this.state.x = this._rng ? this._rng.int(255) : 0;
        this.state.y = this._rng ? this._rng.int(255) : 0;
        this.state.s = 253;
        this.state.p = this._rng ? this._rng.int(65535) : 0;
        this.state.flags = (this._rng ? this._rng.int(255) : 0) | 4 | 32 | 16;
        this.state.irq = false;
        this.state.nmi = false;
        this.executionState = 0;
        this._interruptPending = false;
        this._nmiPending = false;
        this._halt = false;
        this._lastResult = this._opBoot.reset(void 0);
        this._lastInstructionPointer = 0;
        return this;
      }
      setInterrupt(i) {
        this._interruptPending = i;
        return this;
      }
      isInterrupt() {
        return this._interruptPending;
      }
      nmi() {
        this._nmiPending = true;
        return this;
      }
      halt() {
        this._halt = true;
        return this;
      }
      resume() {
        this._halt = false;
        return this;
      }
      isHalt() {
        return this._halt;
      }
      setInvalidInstructionCallback(callback) {
        this._invalidInstructionCallback = callback;
        return this;
      }
      getInvalidInstructionCallback() {
        return this._invalidInstructionCallback;
      }
      getLastInstructionPointer() {
        return this._lastInstructionPointer;
      }
      cycle() {
        if (this._halt && (!this._lastResult || this._lastResult.cycleType === 0)) {
          return this;
        }
        if (this.executionState === 1) {
          this._fetch();
          return this;
        }
        let value;
        switch (this._lastResult.cycleType) {
          case 0:
            value = this._bus.read(this._lastResult.address);
            break;
          case 1:
            value = this._lastResult.value;
            this._bus.write(this._lastResult.address, value);
            break;
          default:
            throw new Error("invalid cycle type");
        }
        if (this._lastResult.pollInterrupts) {
          this._pollInterrupts();
          this._lastResult.pollInterrupts = false;
          this._pollInterruptsAfterLastInstruction = false;
        }
        this._lastResult = this._lastResult.nextStep(value);
        if (this._lastResult === null) {
          this.executionState = 1;
        }
        return this;
      }
      _fetch() {
        if (this._pollInterruptsAfterLastInstruction) {
          this._pollInterrupts();
        }
        this._lastInstructionPointer = this.state.p;
        let operation;
        const opcode = this._bus.read(this.state.p);
        if (this.state.nmi) {
          operation = this._opNmi;
          this._pollInterruptsAfterLastInstruction = false;
        } else if (this.state.irq) {
          operation = this._opIrq;
          this._pollInterruptsAfterLastInstruction = false;
        } else {
          operation = this._operations[opcode];
          this.state.p = this.state.p + 1 & 65535;
          this._pollInterruptsAfterLastInstruction = true;
        }
        if (!operation) {
          if (this._invalidInstructionCallback) {
            this._invalidInstructionCallback(this);
          }
          return;
        }
        this.executionState = 2;
        this._lastResult = operation.reset(void 0);
      }
      _pollInterrupts() {
        this.state.irq = false;
        if (this._nmiPending) {
          this.state.nmi = true;
          this._nmiPending = false;
          return;
        }
        if (this._interruptPending && !this.state.nmi && !(this.state.flags & 4)) {
          this.state.irq = true;
        }
      }
    };
    exports.default = StateMachineCpu;
  }
});

// node_modules/6502.ts/lib/machine/cpu/ops.js
var require_ops2 = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/ops.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.opTxa = exports.opTsx = exports.opTay = exports.opTax = exports.opSty = exports.opStx = exports.opSta = exports.opSei = exports.opSed = exports.opSec = exports.opSbc = exports.opRts = exports.opRti = exports.opRorMem = exports.opRorAcc = exports.opRolMem = exports.opRolAcc = exports.opPla = exports.opPha = exports.opPlp = exports.opPhp = exports.opOra = exports.opNop = exports.opLsrMem = exports.opLsrAcc = exports.opLdy = exports.opLdx = exports.opLda = exports.opJsr = exports.opJmp = exports.opIny = exports.opInx = exports.opInc = exports.opDey = exports.opEor = exports.opDex = exports.opDec = exports.opCpy = exports.opCpx = exports.opCmp = exports.opClv = exports.opCli = exports.opCld = exports.opClc = exports.opBrk = exports.opBit = exports.opAslMem = exports.opAslAcc = exports.opAnd = exports.opAdc = void 0;
    exports.opRla = exports.opRra = exports.opAtx = exports.opAac = exports.opIsc = exports.opLar = exports.opAax = exports.opSlo = exports.opArr = exports.opLax = exports.opDcp = exports.opAxs = exports.opAlr = exports.opTya = exports.opTxs = void 0;
    function restoreFlagsFromStack(state, bus) {
      state.s = state.s + 1 & 255;
      state.flags = (bus.read(256 + state.s) | 32) & ~16;
    }
    function setFlagsNZ(state, operand) {
      state.flags = state.flags & ~(128 | 2) | operand & 128 | (operand ? 0 : 2);
    }
    function opAdc(state, bus, operand) {
      if (state.flags & 8) {
        const d0 = (operand & 15) + (state.a & 15) + (state.flags & 1), d1 = (operand >>> 4) + (state.a >>> 4) + (d0 > 9 ? 1 : 0);
        state.a = d0 % 10 | d1 % 10 << 4;
        state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | (d1 > 9 ? 1 : 0);
      } else {
        const sum = state.a + operand + (state.flags & 1), result = sum & 255;
        state.flags = state.flags & ~(128 | 2 | 1 | 64) | result & 128 | (result ? 0 : 2) | sum >>> 8 | (~(operand ^ state.a) & (result ^ operand) & 128) >>> 1;
        state.a = result;
      }
    }
    exports.opAdc = opAdc;
    function opAnd(state, bus, operand) {
      state.a &= operand;
      setFlagsNZ(state, state.a);
    }
    exports.opAnd = opAnd;
    function opAslAcc(state) {
      const old = state.a;
      state.a = state.a << 1 & 255;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old >>> 7;
    }
    exports.opAslAcc = opAslAcc;
    function opAslMem(state, bus, operand) {
      const old = bus.read(operand), value = old << 1 & 255;
      bus.write(operand, value);
      state.flags = state.flags & ~(128 | 2 | 1) | value & 128 | (value ? 0 : 2) | old >>> 7;
    }
    exports.opAslMem = opAslMem;
    function opBit(state, bus, operand) {
      state.flags = state.flags & ~(128 | 64 | 2) | operand & (128 | 64) | (operand & state.a ? 0 : 2);
    }
    exports.opBit = opBit;
    function opBrk(state, bus) {
      const nextOpAddr = state.p + 1 & 65535;
      let vector = 65534;
      if (state.nmi) {
        vector = 65530;
        state.nmi = false;
      }
      state.nmi = state.irq = false;
      bus.write(state.s + 256, nextOpAddr >>> 8 & 255);
      state.s = state.s + 255 & 255;
      bus.write(state.s + 256, nextOpAddr & 255);
      state.s = state.s + 255 & 255;
      bus.write(state.s + 256, state.flags | 16);
      state.s = state.s + 255 & 255;
      state.flags |= 4;
      state.p = bus.readWord(vector);
    }
    exports.opBrk = opBrk;
    function opClc(state) {
      state.flags &= ~1;
    }
    exports.opClc = opClc;
    function opCld(state) {
      state.flags &= ~8;
    }
    exports.opCld = opCld;
    function opCli(state) {
      state.flags &= ~4;
    }
    exports.opCli = opCli;
    function opClv(state) {
      state.flags &= ~64;
    }
    exports.opClv = opClv;
    function opCmp(state, bus, operand) {
      const diff = state.a + (~operand & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
    }
    exports.opCmp = opCmp;
    function opCpx(state, bus, operand) {
      const diff = state.x + (~operand & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
    }
    exports.opCpx = opCpx;
    function opCpy(state, bus, operand) {
      const diff = state.y + (~operand & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
    }
    exports.opCpy = opCpy;
    function opDec(state, bus, operand) {
      const value = bus.read(operand) + 255 & 255;
      bus.write(operand, value);
      setFlagsNZ(state, value);
    }
    exports.opDec = opDec;
    function opDex(state) {
      state.x = state.x + 255 & 255;
      setFlagsNZ(state, state.x);
    }
    exports.opDex = opDex;
    function opEor(state, bus, operand) {
      state.a = state.a ^ operand;
      setFlagsNZ(state, state.a);
    }
    exports.opEor = opEor;
    function opDey(state) {
      state.y = state.y + 255 & 255;
      setFlagsNZ(state, state.y);
    }
    exports.opDey = opDey;
    function opInc(state, bus, operand) {
      const value = bus.read(operand) + 1 & 255;
      bus.write(operand, value);
      setFlagsNZ(state, value);
    }
    exports.opInc = opInc;
    function opInx(state) {
      state.x = state.x + 1 & 255;
      setFlagsNZ(state, state.x);
    }
    exports.opInx = opInx;
    function opIny(state) {
      state.y = state.y + 1 & 255;
      setFlagsNZ(state, state.y);
    }
    exports.opIny = opIny;
    function opJmp(state, bus, operand) {
      state.p = operand;
    }
    exports.opJmp = opJmp;
    function opJsr(state, bus, operand) {
      const returnPtr = state.p + 1 & 65535, addrLo = bus.read(state.p);
      bus.read(256 + state.s);
      bus.write(256 + state.s, returnPtr >>> 8);
      state.s = state.s + 255 & 255;
      bus.write(256 + state.s, returnPtr & 255);
      state.s = state.s + 255 & 255;
      state.p = addrLo | bus.read(state.p + 1 & 65535) << 8;
    }
    exports.opJsr = opJsr;
    function opLda(state, bus, operand, addressingMode) {
      state.a = addressingMode === 1 ? operand : bus.read(operand);
      setFlagsNZ(state, state.a);
    }
    exports.opLda = opLda;
    function opLdx(state, bus, operand, addressingMode) {
      state.x = addressingMode === 1 ? operand : bus.read(operand);
      setFlagsNZ(state, state.x);
    }
    exports.opLdx = opLdx;
    function opLdy(state, bus, operand, addressingMode) {
      state.y = addressingMode === 1 ? operand : bus.read(operand);
      setFlagsNZ(state, state.y);
    }
    exports.opLdy = opLdy;
    function opLsrAcc(state) {
      const old = state.a;
      state.a = state.a >>> 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old & 1;
    }
    exports.opLsrAcc = opLsrAcc;
    function opLsrMem(state, bus, operand) {
      const old = bus.read(operand), value = old >>> 1;
      bus.write(operand, value);
      state.flags = state.flags & ~(128 | 2 | 1) | value & 128 | (value ? 0 : 2) | old & 1;
    }
    exports.opLsrMem = opLsrMem;
    function opNop() {
    }
    exports.opNop = opNop;
    function opOra(state, bus, operand) {
      state.a |= operand;
      setFlagsNZ(state, state.a);
    }
    exports.opOra = opOra;
    function opPhp(state, bus) {
      bus.write(256 + state.s, state.flags | 16);
      state.s = state.s + 255 & 255;
    }
    exports.opPhp = opPhp;
    function opPlp(state, bus) {
      restoreFlagsFromStack(state, bus);
    }
    exports.opPlp = opPlp;
    function opPha(state, bus) {
      bus.write(256 + state.s, state.a);
      state.s = state.s + 255 & 255;
    }
    exports.opPha = opPha;
    function opPla(state, bus) {
      state.s = state.s + 1 & 255;
      state.a = bus.read(256 + state.s);
      setFlagsNZ(state, state.a);
    }
    exports.opPla = opPla;
    function opRolAcc(state) {
      const old = state.a;
      state.a = state.a << 1 & 255 | state.flags & 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old >>> 7;
    }
    exports.opRolAcc = opRolAcc;
    function opRolMem(state, bus, operand) {
      const old = bus.read(operand), value = old << 1 & 255 | state.flags & 1;
      bus.write(operand, value);
      state.flags = state.flags & ~(128 | 2 | 1) | value & 128 | (value ? 0 : 2) | old >>> 7;
    }
    exports.opRolMem = opRolMem;
    function opRorAcc(state) {
      const old = state.a;
      state.a = state.a >>> 1 | (state.flags & 1) << 7;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | old & 1;
    }
    exports.opRorAcc = opRorAcc;
    function opRorMem(state, bus, operand) {
      const old = bus.read(operand), value = old >>> 1 | (state.flags & 1) << 7;
      bus.write(operand, value);
      state.flags = state.flags & ~(128 | 2 | 1) | value & 128 | (value ? 0 : 2) | old & 1;
    }
    exports.opRorMem = opRorMem;
    function opRti(state, bus) {
      let returnPtr;
      restoreFlagsFromStack(state, bus);
      state.s = state.s + 1 & 255;
      returnPtr = bus.read(256 + state.s);
      state.s = state.s + 1 & 255;
      returnPtr |= bus.read(256 + state.s) << 8;
      state.p = returnPtr;
    }
    exports.opRti = opRti;
    function opRts(state, bus) {
      let returnPtr;
      bus.read(256 + state.s);
      state.s = state.s + 1 & 255;
      returnPtr = bus.read(256 + state.s);
      state.s = state.s + 1 & 255;
      returnPtr += bus.read(256 + state.s) << 8;
      state.p = returnPtr + 1 & 65535;
    }
    exports.opRts = opRts;
    function opSbc(state, bus, operand) {
      if (state.flags & 8) {
        const d0 = (state.a & 15) - (operand & 15) - (~state.flags & 1), d1 = (state.a >>> 4) - (operand >>> 4) - (d0 < 0 ? 1 : 0);
        state.a = (d0 < 0 ? 10 + d0 : d0) | (d1 < 0 ? 10 + d1 : d1) << 4;
        state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | (d1 < 0 ? 0 : 1);
      } else {
        operand = ~operand & 255;
        const sum = state.a + operand + (state.flags & 1), result = sum & 255;
        state.flags = state.flags & ~(128 | 2 | 1 | 64) | result & 128 | (result ? 0 : 2) | sum >>> 8 | (~(operand ^ state.a) & (result ^ operand) & 128) >>> 1;
        state.a = result;
      }
    }
    exports.opSbc = opSbc;
    function opSec(state) {
      state.flags |= 1;
    }
    exports.opSec = opSec;
    function opSed(state) {
      state.flags |= 8;
    }
    exports.opSed = opSed;
    function opSei(state) {
      state.flags |= 4;
    }
    exports.opSei = opSei;
    function opSta(state, bus, operand) {
      bus.write(operand, state.a);
    }
    exports.opSta = opSta;
    function opStx(state, bus, operand) {
      bus.write(operand, state.x);
    }
    exports.opStx = opStx;
    function opSty(state, bus, operand) {
      bus.write(operand, state.y);
    }
    exports.opSty = opSty;
    function opTax(state) {
      state.x = state.a;
      setFlagsNZ(state, state.a);
    }
    exports.opTax = opTax;
    function opTay(state) {
      state.y = state.a;
      setFlagsNZ(state, state.a);
    }
    exports.opTay = opTay;
    function opTsx(state) {
      state.x = state.s;
      setFlagsNZ(state, state.x);
    }
    exports.opTsx = opTsx;
    function opTxa(state) {
      state.a = state.x;
      setFlagsNZ(state, state.a);
    }
    exports.opTxa = opTxa;
    function opTxs(state) {
      state.s = state.x;
    }
    exports.opTxs = opTxs;
    function opTya(state) {
      state.a = state.y;
      setFlagsNZ(state, state.a);
    }
    exports.opTya = opTya;
    function opAlr(state, bus, operand) {
      const i = state.a & operand;
      state.a = i >>> 1;
      state.flags = state.flags & ~(128 | 2 | 1) | state.a & 128 | (state.a ? 0 : 2) | i & 1;
    }
    exports.opAlr = opAlr;
    function opAxs(state, bus, operand) {
      const value = (state.a & state.x) + (~operand & 255) + 1;
      state.x = value & 255;
      state.flags = state.flags & ~(128 | 2 | 1) | state.x & 128 | (state.x & 255 ? 0 : 2) | value >>> 8;
    }
    exports.opAxs = opAxs;
    function opDcp(state, bus, operand) {
      const value = bus.read(operand) + 255 & 255;
      bus.write(operand, value);
      const diff = state.a + (~value & 255) + 1;
      state.flags = state.flags & ~(128 | 2 | 1) | diff & 128 | (diff & 255 ? 0 : 2) | diff >>> 8;
    }
    exports.opDcp = opDcp;
    function opLax(state, bus, operand) {
      state.a = operand;
      state.x = operand;
      setFlagsNZ(state, operand);
    }
    exports.opLax = opLax;
    function opArr(state, bus, operand) {
      state.a = (state.a & operand) >>> 1 | (state.flags & 1 ? 128 : 0);
      state.flags = state.flags & ~(1 | 128 | 2 | 64) | (state.a & 64) >>> 6 | (state.a ? 0 : 2) | state.a & 128 | state.a & 64 ^ (state.a & 32) << 1;
    }
    exports.opArr = opArr;
    function opSlo(state, bus, operand) {
      let value = bus.read(operand);
      state.flags = state.flags & ~1 | value >>> 7;
      value = value << 1 & 255;
      bus.write(operand, value);
      state.a = state.a | value;
      setFlagsNZ(state, state.a);
    }
    exports.opSlo = opSlo;
    function opAax(state, bus, operand) {
      const value = state.x & state.a;
      bus.write(operand, value);
      setFlagsNZ(state, value);
    }
    exports.opAax = opAax;
    function opLar(state, bus, operand) {
      state.s = state.a = state.x = state.s & operand;
      setFlagsNZ(state, state.a);
    }
    exports.opLar = opLar;
    function opIsc(state, bus, operand) {
      const value = bus.read(operand) + 1 & 255;
      bus.write(operand, value);
      opSbc(state, bus, value);
    }
    exports.opIsc = opIsc;
    function opAac(state, bus, operand) {
      state.a &= operand;
      setFlagsNZ(state, state.a);
      state.flags = state.flags & ~1 | (state.a & 128) >>> 7;
    }
    exports.opAac = opAac;
    function opAtx(state, bus, operand) {
      state.a &= operand;
      state.x = state.a;
      setFlagsNZ(state, state.a);
    }
    exports.opAtx = opAtx;
    function opRra(state, bus, operand) {
      const old = bus.read(operand), value = old >>> 1 | (state.flags & 1) << 7;
      bus.write(operand, value);
      state.flags = state.flags & ~1 | old & 1;
      opAdc(state, bus, value);
    }
    exports.opRra = opRra;
    function opRla(state, bus, operand) {
      const old = bus.read(operand), value = old << 1 & 255 | state.flags & 1;
      bus.write(operand, value);
      state.flags = state.flags & ~1 | old >>> 7;
      opAnd(state, bus, value);
    }
    exports.opRla = opRla;
  }
});

// node_modules/6502.ts/lib/machine/cpu/BatchedAccessCpu.js
var require_BatchedAccessCpu = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/BatchedAccessCpu.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = exports.opNmi = exports.opIrq = exports.opBoot = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Instruction_1 = tslib_1.__importDefault(require_Instruction());
    var CpuInterface_1 = tslib_1.__importDefault(require_CpuInterface());
    var ops = tslib_1.__importStar(require_ops2());
    function opBoot(state, bus) {
      state.p = bus.readWord(65532);
    }
    exports.opBoot = opBoot;
    function dispatchInterrupt(state, bus, vector) {
      const nextOpAddr = state.p;
      if (state.nmi) {
        vector = 65530;
      }
      state.nmi = state.irq = false;
      bus.write(state.s + 256, nextOpAddr >>> 8 & 255);
      state.s = state.s + 255 & 255;
      bus.write(state.s + 256, nextOpAddr & 255);
      state.s = state.s + 255 & 255;
      bus.write(state.s + 256, state.flags & ~16);
      state.s = state.s + 255 & 255;
      state.flags |= 4;
      state.p = bus.readWord(vector);
    }
    function opIrq(state, bus) {
      dispatchInterrupt(state, bus, 65534);
    }
    exports.opIrq = opIrq;
    function opNmi(state, bus) {
      dispatchInterrupt(state, bus, 65530);
    }
    exports.opNmi = opNmi;
    var BatchedAccessCpu = class {
      constructor(_bus, _rng) {
        this._bus = _bus;
        this._rng = _rng;
        this.executionState = 0;
        this.state = new CpuInterface_1.default.State();
        this._opCycles = 0;
        this._instructionCallback = null;
        this._invalidInstructionCallback = null;
        this._interruptPending = false;
        this._nmiPending = false;
        this._interuptCheck = 0;
        this._halted = false;
        this._operand = 0;
        this._lastInstructionPointer = 0;
        this._currentAddressingMode = 12;
        this._dereference = false;
        this.reset();
      }
      setInterrupt(irq) {
        this._interruptPending = irq;
        return this;
      }
      isInterrupt() {
        return this._interruptPending;
      }
      nmi() {
        this._nmiPending = true;
        return this;
      }
      halt() {
        this._halted = true;
        return this;
      }
      resume() {
        this._halted = false;
        return this;
      }
      isHalt() {
        return this._halted;
      }
      setInvalidInstructionCallback(callback) {
        this._invalidInstructionCallback = callback;
        return this;
      }
      getInvalidInstructionCallback() {
        return this._invalidInstructionCallback;
      }
      getLastInstructionPointer() {
        return this._lastInstructionPointer;
      }
      reset() {
        this.state.a = this._rng ? this._rng.int(255) : 0;
        this.state.x = this._rng ? this._rng.int(255) : 0;
        this.state.y = this._rng ? this._rng.int(255) : 0;
        this.state.s = 253;
        this.state.p = this._rng ? this._rng.int(65535) : 0;
        this.state.flags = (this._rng ? this._rng.int(255) : 0) | 4 | 32 | 16;
        this.state.irq = false;
        this.state.nmi = false;
        this.executionState = 0;
        this._opCycles = 7;
        this._interruptPending = false;
        this._nmiPending = false;
        this._instructionCallback = opBoot;
        return this;
      }
      cycle() {
        if (this._halted) {
          return this;
        }
        switch (this.executionState) {
          case 0:
          case 2:
            if (--this._opCycles === 0) {
              if (this._dereference) {
                this._operand = this._bus.read(this._operand);
              }
              if (this._interuptCheck === 1) {
                this._checkForInterrupts();
              }
              this._instructionCallback(this.state, this._bus, this._operand, this._currentAddressingMode);
              this.executionState = 1;
              if (this._interuptCheck === 0) {
                this._checkForInterrupts();
              }
            }
            break;
          case 1:
            if (this.state.nmi) {
              this._instructionCallback = opNmi;
              this._opCycles = 6;
              this.state.nmi = this.state.irq = false;
              this._interuptCheck = 1;
              this.executionState = 2;
              return this;
            }
            if (this.state.irq) {
              this._instructionCallback = opIrq;
              this._opCycles = 6;
              this.state.nmi = this.state.irq = false;
              this._interuptCheck = 1;
              this.executionState = 2;
              return this;
            }
            this._fetch();
            break;
        }
        return this;
      }
      _fetch() {
        const instruction = Instruction_1.default.opcodes[this._bus.read(this.state.p)];
        let addressingMode = instruction.addressingMode, dereference = false, slowIndexedAccess = false;
        this._lastInstructionPointer = this.state.p;
        this._currentAddressingMode = addressingMode;
        this._interuptCheck = 0;
        switch (instruction.operation) {
          case 0:
            this._opCycles = 0;
            this._instructionCallback = ops.opAdc;
            dereference = true;
            break;
          case 1:
            this._opCycles = 0;
            this._instructionCallback = ops.opAnd;
            dereference = true;
            break;
          case 2:
            if (addressingMode === 0) {
              this._opCycles = 1;
              this._instructionCallback = ops.opAslAcc;
            } else {
              this._opCycles = 3;
              this._instructionCallback = ops.opAslMem;
              slowIndexedAccess = true;
            }
            break;
          case 3:
            if (this.state.flags & 1) {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            } else {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            }
            break;
          case 4:
            if (this.state.flags & 1) {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            } else {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            }
            break;
          case 5:
            if (this.state.flags & 2) {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            } else {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            }
            break;
          case 6:
            this._opCycles = 0;
            this._instructionCallback = ops.opBit;
            dereference = true;
            break;
          case 7:
            if (this.state.flags & 128) {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            } else {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            }
            break;
          case 8:
            if (this.state.flags & 2) {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            } else {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            }
            break;
          case 9:
            if (this.state.flags & 128) {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            } else {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            }
            break;
          case 11:
            if (this.state.flags & 64) {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            } else {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            }
            break;
          case 12:
            if (this.state.flags & 64) {
              this._instructionCallback = ops.opJmp;
              this._opCycles = 0;
            } else {
              addressingMode = 0;
              this._instructionCallback = ops.opNop;
              this.state.p = this.state.p + 1 & 65535;
              this._opCycles = 1;
            }
            break;
          case 10:
            this._opCycles = 6;
            this._instructionCallback = ops.opBrk;
            this._interuptCheck = 1;
            break;
          case 13:
            this._opCycles = 1;
            this._instructionCallback = ops.opClc;
            break;
          case 14:
            this._opCycles = 1;
            this._instructionCallback = ops.opCld;
            break;
          case 15:
            this._opCycles = 1;
            this._instructionCallback = ops.opCli;
            this._interuptCheck = 1;
            break;
          case 16:
            this._opCycles = 1;
            this._instructionCallback = ops.opClv;
            break;
          case 17:
            this._opCycles = 0;
            this._instructionCallback = ops.opCmp;
            dereference = true;
            break;
          case 18:
            this._opCycles = 0;
            this._instructionCallback = ops.opCpx;
            dereference = true;
            break;
          case 19:
            this._opCycles = 0;
            this._instructionCallback = ops.opCpy;
            dereference = true;
            break;
          case 20:
            this._opCycles = 3;
            this._instructionCallback = ops.opDec;
            slowIndexedAccess = true;
            break;
          case 21:
            this._opCycles = 1;
            this._instructionCallback = ops.opDex;
            break;
          case 22:
            this._opCycles = 1;
            this._instructionCallback = ops.opDey;
            break;
          case 23:
            this._opCycles = 0;
            this._instructionCallback = ops.opEor;
            dereference = true;
            break;
          case 24:
            this._opCycles = 3;
            this._instructionCallback = ops.opInc;
            slowIndexedAccess = true;
            break;
          case 25:
            this._opCycles = 1;
            this._instructionCallback = ops.opInx;
            break;
          case 26:
            this._opCycles = 1;
            this._instructionCallback = ops.opIny;
            break;
          case 27:
            this._opCycles = 0;
            this._instructionCallback = ops.opJmp;
            break;
          case 28:
            this._opCycles = 5;
            this._instructionCallback = ops.opJsr;
            break;
          case 29:
            this._opCycles = addressingMode === 1 ? 0 : 1;
            this._instructionCallback = ops.opLda;
            break;
          case 30:
            this._opCycles = addressingMode === 1 ? 0 : 1;
            this._instructionCallback = ops.opLdx;
            break;
          case 31:
            this._opCycles = addressingMode === 1 ? 0 : 1;
            this._instructionCallback = ops.opLdy;
            break;
          case 32:
            if (addressingMode === 0) {
              this._opCycles = 1;
              this._instructionCallback = ops.opLsrAcc;
            } else {
              this._opCycles = 3;
              this._instructionCallback = ops.opLsrMem;
              slowIndexedAccess = true;
            }
            break;
          case 33:
            this._opCycles = 1;
            this._instructionCallback = ops.opNop;
            break;
          case 56:
          case 57:
            this._opCycles = 0;
            dereference = true;
            this._instructionCallback = ops.opNop;
            break;
          case 34:
            this._opCycles = 0;
            this._instructionCallback = ops.opOra;
            dereference = true;
            break;
          case 36:
            this._opCycles = 2;
            this._instructionCallback = ops.opPhp;
            break;
          case 35:
            this._opCycles = 2;
            this._instructionCallback = ops.opPha;
            break;
          case 37:
            this._opCycles = 3;
            this._instructionCallback = ops.opPla;
            break;
          case 38:
            this._opCycles = 3;
            this._instructionCallback = ops.opPlp;
            this._interuptCheck = 1;
            break;
          case 39:
            if (addressingMode === 0) {
              this._opCycles = 1;
              this._instructionCallback = ops.opRolAcc;
            } else {
              this._opCycles = 3;
              this._instructionCallback = ops.opRolMem;
              slowIndexedAccess = true;
            }
            break;
          case 40:
            if (addressingMode === 0) {
              this._opCycles = 1;
              this._instructionCallback = ops.opRorAcc;
            } else {
              this._opCycles = 3;
              this._instructionCallback = ops.opRorMem;
              slowIndexedAccess = true;
            }
            break;
          case 41:
            this._opCycles = 5;
            this._instructionCallback = ops.opRti;
            break;
          case 42:
            this._opCycles = 5;
            this._instructionCallback = ops.opRts;
            break;
          case 43:
            this._opCycles = 0;
            this._instructionCallback = ops.opSbc;
            dereference = true;
            break;
          case 44:
            this._opCycles = 1;
            this._instructionCallback = ops.opSec;
            break;
          case 45:
            this._opCycles = 1;
            this._instructionCallback = ops.opSed;
            break;
          case 46:
            this._opCycles = 1;
            this._instructionCallback = ops.opSei;
            this._interuptCheck = 1;
            break;
          case 47:
            this._opCycles = 1;
            this._instructionCallback = ops.opSta;
            slowIndexedAccess = true;
            break;
          case 48:
            this._opCycles = 1;
            this._instructionCallback = ops.opStx;
            slowIndexedAccess = true;
            break;
          case 49:
            this._opCycles = 1;
            this._instructionCallback = ops.opSty;
            slowIndexedAccess = true;
            break;
          case 50:
            this._opCycles = 1;
            this._instructionCallback = ops.opTax;
            break;
          case 51:
            this._opCycles = 1;
            this._instructionCallback = ops.opTay;
            break;
          case 52:
            this._opCycles = 1;
            this._instructionCallback = ops.opTsx;
            break;
          case 53:
            this._opCycles = 1;
            this._instructionCallback = ops.opTxa;
            break;
          case 54:
            this._opCycles = 1;
            this._instructionCallback = ops.opTxs;
            break;
          case 55:
            this._opCycles = 1;
            this._instructionCallback = ops.opTya;
            break;
          case 62:
            this._opCycles = 0;
            this._instructionCallback = ops.opArr;
            break;
          case 58:
            this._opCycles = 0;
            this._instructionCallback = ops.opAlr;
            break;
          case 59:
            this._opCycles = 0;
            this._instructionCallback = ops.opAxs;
            break;
          case 60:
            this._opCycles = 3;
            this._instructionCallback = ops.opDcp;
            slowIndexedAccess = true;
            break;
          case 61:
            this._opCycles = 0;
            this._instructionCallback = ops.opLax;
            dereference = true;
            break;
          case 63:
            this._opCycles = 3;
            this._instructionCallback = ops.opSlo;
            slowIndexedAccess = true;
            dereference = false;
            break;
          case 64:
            this._opCycles = 1;
            this._instructionCallback = ops.opAax;
            break;
          case 65:
            this._opCycles = 0;
            this._instructionCallback = ops.opLar;
            dereference = true;
            break;
          case 66:
            this._opCycles = 3;
            this._instructionCallback = ops.opIsc;
            slowIndexedAccess = true;
            break;
          case 67:
            this._opCycles = 0;
            this._instructionCallback = ops.opAac;
            break;
          case 68:
            this._opCycles = 0;
            this._instructionCallback = ops.opAtx;
            break;
          case 69:
            this._opCycles = 3;
            dereference = false;
            slowIndexedAccess = true;
            this._instructionCallback = ops.opRra;
            break;
          case 70:
            this._opCycles = 3;
            dereference = false;
            slowIndexedAccess = true;
            this._instructionCallback = ops.opRla;
            break;
          default:
            if (this._invalidInstructionCallback) {
              this._invalidInstructionCallback(this);
            }
            return;
        }
        this.state.p = this.state.p + 1 & 65535;
        let value, base;
        switch (addressingMode) {
          case 1:
            this._operand = this._bus.read(this.state.p);
            dereference = false;
            this.state.p = this.state.p + 1 & 65535;
            this._opCycles++;
            break;
          case 2:
            this._operand = this._bus.read(this.state.p);
            this.state.p = this.state.p + 1 & 65535;
            this._opCycles++;
            break;
          case 3:
            this._operand = this._bus.readWord(this.state.p);
            this.state.p = this.state.p + 2 & 65535;
            this._opCycles += 2;
            break;
          case 4:
            value = this._bus.readWord(this.state.p);
            if ((value & 255) === 255) {
              this._operand = this._bus.read(value) + (this._bus.read(value & 65280) << 8);
            } else {
              this._operand = this._bus.readWord(value);
            }
            this.state.p = this.state.p + 2 & 65535;
            this._opCycles += 4;
            break;
          case 5:
            value = this._bus.read(this.state.p);
            value = value & 128 ? -(~(value - 1) & 255) : value;
            this._operand = this.state.p + value + 65537 & 65535;
            this.state.p = this.state.p + 1 & 65535;
            this._opCycles += (this._operand & 65280) !== (this.state.p & 65280) ? 3 : 2;
            break;
          case 6:
            base = this._bus.read(this.state.p);
            this._bus.read(base);
            this._operand = base + this.state.x & 255;
            this.state.p = this.state.p + 1 & 65535;
            this._opCycles += 2;
            break;
          case 7:
            value = this._bus.readWord(this.state.p);
            this._operand = value + this.state.x & 65535;
            if ((this._operand & 65280) !== (value & 65280)) {
              this._bus.read(value & 65280 | this._operand & 255);
            }
            this._opCycles += slowIndexedAccess || (this._operand & 65280) !== (value & 65280) ? 3 : 2;
            this.state.p = this.state.p + 2 & 65535;
            break;
          case 9:
            base = this._bus.read(this.state.p);
            this._bus.read(base);
            this._operand = base + this.state.y & 255;
            this.state.p = this.state.p + 1 & 65535;
            this._opCycles += 2;
            break;
          case 10:
            value = this._bus.readWord(this.state.p);
            this._operand = value + this.state.y & 65535;
            if ((this._operand & 65280) !== (value & 65280)) {
              this._bus.read(value & 65280 | this._operand & 255);
            }
            this._opCycles += slowIndexedAccess || (this._operand & 65280) !== (value & 65280) ? 3 : 2;
            this.state.p = this.state.p + 2 & 65535;
            break;
          case 8:
            base = this._bus.read(this.state.p);
            this._bus.read(base);
            value = base + this.state.x & 255;
            if (value === 255) {
              this._operand = this._bus.read(255) + (this._bus.read(0) << 8);
            } else {
              this._operand = this._bus.readWord(value);
            }
            this._opCycles += 4;
            this.state.p = this.state.p + 1 & 65535;
            break;
          case 11:
            value = this._bus.read(this.state.p);
            if (value === 255) {
              value = this._bus.read(255) + (this._bus.read(0) << 8);
            } else {
              value = this._bus.readWord(value);
            }
            this._operand = value + this.state.y & 65535;
            if ((this._operand & 65280) !== (value & 65280)) {
              this._bus.read(value & 65280 | this._operand & 255);
            }
            this._opCycles += slowIndexedAccess || (value & 65280) !== (this._operand & 65280) ? 4 : 3;
            this.state.p = this.state.p + 1 & 65535;
            break;
        }
        this._dereference = dereference;
        if (dereference) {
          this._opCycles++;
        }
        this.executionState = 2;
      }
      _checkForInterrupts() {
        if (this._nmiPending) {
          this.state.irq = false;
          this.state.nmi = true;
          this._nmiPending = false;
        }
        if (this._interruptPending && !this.state.nmi && !(this.state.flags & 4)) {
          this.state.irq = true;
        }
      }
    };
    exports.default = BatchedAccessCpu;
  }
});

// node_modules/6502.ts/lib/machine/cpu/Factory.js
var require_Factory = __commonJS({
  "node_modules/6502.ts/lib/machine/cpu/Factory.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var StateMachineCpu_1 = tslib_1.__importDefault(require_StateMachineCpu());
    var BatchedAccessCpu_1 = tslib_1.__importDefault(require_BatchedAccessCpu());
    var Factory = class _Factory {
      constructor(_type) {
        this._type = _type;
      }
      create(bus, rng) {
        switch (this._type) {
          case _Factory.Type.stateMachine:
            return new StateMachineCpu_1.default(bus, rng);
          case _Factory.Type.batchedAccess:
            return new BatchedAccessCpu_1.default(bus, rng);
          default:
            throw new Error("invalid CPU type");
        }
      }
    };
    (function(Factory2) {
      let Type;
      (function(Type2) {
        Type2[Type2["stateMachine"] = 0] = "stateMachine";
        Type2[Type2["batchedAccess"] = 1] = "batchedAccess";
      })(Type = Factory2.Type || (Factory2.Type = {}));
    })(Factory || (Factory = {}));
    exports.default = Factory;
  }
});

// node_modules/6502.ts/lib/machine/stella/Config.js
var require_Config = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/Config.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Factory_1 = tslib_1.__importDefault(require_Factory());
    var Config2;
    (function(Config3) {
      function create(config = {}) {
        return Object.assign({ tvMode: 0, enableAudio: true, randomSeed: -1, emulatePaddles: true, frameStart: -1, pcmAudio: false, cpuType: Factory_1.default.Type.stateMachine }, config);
      }
      Config3.create = create;
      function getClockHz(config) {
        switch (config.tvMode) {
          case 0:
            return 262 * 228 * 60;
          case 1:
          case 2:
            return 312 * 228 * 50;
        }
      }
      Config3.getClockHz = getClockHz;
    })(Config2 || (Config2 = {}));
    exports.default = Config2;
  }
});

// node_modules/6502.ts/lib/tools/AudioOutputBuffer.js
var require_AudioOutputBuffer = __commonJS({
  "node_modules/6502.ts/lib/tools/AudioOutputBuffer.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var AudioOutputBuffer = class {
      constructor(_content, _sampleRate) {
        this._content = _content;
        this._sampleRate = _sampleRate;
      }
      getLength() {
        return this._content.length;
      }
      getContent() {
        return this._content;
      }
      getSampleRate() {
        return this._sampleRate;
      }
      replaceUnderlyingBuffer(buffer) {
        this._content = buffer;
      }
    };
    exports.default = AudioOutputBuffer;
  }
});

// node_modules/6502.ts/lib/tools/base64.js
var require_base64 = __commonJS({
  "node_modules/6502.ts/lib/tools/base64.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.decode = exports.__init = void 0;
    var encodingsString = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    var encodings = new Uint8Array(256);
    var __init;
    (function(__init2) {
      let i;
      for (i = 0; i < 256; i++) {
        encodings[i] = 255;
      }
      for (i = 0; i < 64; i++) {
        encodings[encodingsString.charCodeAt(i)] = i;
      }
      encodings["=".charCodeAt(0)] = 0;
    })(__init = exports.__init || (exports.__init = {}));
    function decodeChar(data, idx) {
      const value = encodings[data.charCodeAt(idx)];
      if (value > 63) {
        throw new Error('invalid base64 character "' + data[idx] + '" at index ' + idx);
      }
      return value;
    }
    function decodeNibble(data, idx) {
      return (decodeChar(data, idx) << 18) + (decodeChar(data, idx + 1) << 12) + (decodeChar(data, idx + 2) << 6) + decodeChar(data, idx + 3);
    }
    function getPadding(data) {
      let padding = 0, idx = data.length - 1;
      while (idx >= 0 && data[idx--] === "=") {
        padding++;
      }
      return padding;
    }
    function decode(data) {
      if (data.length % 4 !== 0) {
        throw new Error("invalid base64 data --- char count mismatch");
      }
      const nibbles = data.length / 4, decodedSize = nibbles * 3 - getPadding(data), decoded = new Uint8Array(decodedSize);
      let idx = 0;
      for (let i = 0; i < nibbles; i++) {
        const nibble = decodeNibble(data, i * 4);
        for (let j = 0; j < 3 && idx < decodedSize; j++) {
          decoded[idx++] = nibble >>> 8 * (2 - j) & 255;
        }
      }
      return decoded;
    }
    exports.decode = decode;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/ToneGenerator.js
var require_ToneGenerator = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/ToneGenerator.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Config_1 = tslib_1.__importDefault(require_Config());
    var AudioOutputBuffer_1 = tslib_1.__importDefault(require_AudioOutputBuffer());
    var base64_1 = require_base64();
    var FREQUENCY_DIVISIORS = (0, base64_1.decode)("AQEPAQEBAQEBAQEBAwMDAQ==");
    var POLY0 = new Int8Array([1]);
    var POLY1 = new Int8Array([1, 1]);
    var POLY2 = new Int8Array([16, 15]);
    var POLY4 = (0, base64_1.decode)("AQICAQEBBAM=");
    var POLY5 = (0, base64_1.decode)("AQIBAQICBQQCAQMBAQEBBA==");
    var POLY9 = (0, base64_1.decode)("AQQBAwIEAQIDAgEBAQEBAQIEAgEEAQECAgEDAgEDAQEBBAEBAQECAQECBgECAgECAQIBAQIBBgIBAgIBAQEBAgICAgcCAwICAQEBAwIBAQIBAQcBAQMBAQIDAwEBAQICAQECAgQDBQEDAQEFAgEBAQIBAgEDAQIFAQECAQEBBQEBAQEBAQEBBgEBAQIBAQEBBAIBAQMBAwYDAgMBAQIBAgQBAQEDAQEBAQMBAgEEAgIDBAEBBAECAQICAgEBBAMBBAQJBQQBBQMBAQMCAgIBBQECAQEBAgMBAgEBAwQCBQICAQIDAQEBAQECAQMDAwIBAgEBAQEBAwMBAgIDAQMBCA==");
    var POLY68 = (0, base64_1.decode)("BQYEBQoFAwcECgYDBgQJBg==");
    var POLY465 = (0, base64_1.decode)("AgMCAQQBBgoCBAIBAQQFCQMDBAEBAQgFBQUEAQEBCAQCCAMDAQEHBAIHBQEDAQcEAQQIAgEDBAcBAwcDAgEGBgICBAUDAgYGAQMDAgUDBwMEAwICAgUJAwEFAwECAgsFAQUDAQECDAUBAgUCAQEMBgECBQECAQoGAwICBAECBgo=");
    var POLYS = [
      POLY0,
      POLY4,
      POLY4,
      POLY465,
      POLY1,
      POLY1,
      POLY2,
      POLY5,
      POLY9,
      POLY5,
      POLY2,
      POLY0,
      POLY1,
      POLY1,
      POLY2,
      POLY68
    ];
    var ToneGenerator = class {
      constructor(_config) {
        this._config = _config;
      }
      setConfig(config) {
        this._config = config;
      }
      getKey(tone, frequency) {
        if (POLYS[tone] === POLY1 && FREQUENCY_DIVISIORS[tone] * (frequency + 1) === 1) {
          return 0;
        }
        return tone << 5 | frequency;
      }
      getBuffer(key) {
        const tone = key >>> 5 & 15, frequency = key & 31;
        const poly = POLYS[tone];
        let length = 0;
        for (let i = 0; i < poly.length; i++) {
          length += poly[i];
        }
        length = length * FREQUENCY_DIVISIORS[tone] * (frequency + 1);
        const content = new Float32Array(length);
        const sampleRate = Config_1.default.getClockHz(this._config) / 114;
        let f = 0;
        let count = 0;
        let offset = 0;
        let state = true;
        for (let i = 0; i < length; i++) {
          f++;
          if (f === FREQUENCY_DIVISIORS[tone] * (frequency + 1)) {
            f = 0;
            count++;
            if (count === poly[offset]) {
              offset++;
              count = 0;
              if (poly.length === offset) {
                offset = 0;
              }
            }
            state = !(offset & 1);
          }
          content[i] = state ? 1 : -1;
        }
        return new AudioOutputBuffer_1.default(content, sampleRate);
      }
    };
    exports.default = ToneGenerator;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/WaveformAudio.js
var require_WaveformAudio = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/WaveformAudio.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var ToneGenerator_1 = tslib_1.__importDefault(require_ToneGenerator());
    var WaveformAudio = class {
      constructor(_config) {
        this._config = _config;
        this.bufferChanged = new microevent_ts_1.Event();
        this.volumeChanged = new microevent_ts_1.Event();
        this.stop = new microevent_ts_1.Event();
        this._volume = -1;
        this._tone = -1;
        this._frequency = -1;
        this._active = false;
        this._toneGenerator = null;
        this._toneGenerator = new ToneGenerator_1.default(this._config);
        this.reset();
      }
      reset() {
        this._volume = -1;
        this._tone = -1;
        this._frequency = -1;
      }
      audc(value) {
        value &= 15;
        if (value === this._tone) {
          return;
        }
        this._tone = value;
        this._dispatchBufferChanged();
      }
      audf(value) {
        value &= 31;
        if (value === this._frequency) {
          return;
        }
        this._frequency = value;
        this._dispatchBufferChanged();
      }
      audv(value) {
        value &= 15;
        if (value === this._volume) {
          return;
        }
        this._volume = value / 15;
        this.volumeChanged.dispatch(this._volume);
      }
      setActive(active) {
        this._active = active;
        if (active) {
          this._dispatchBufferChanged();
        } else {
          this.stop.dispatch(void 0);
        }
      }
      getVolume() {
        return this._volume >= 0 ? this._volume : 0;
      }
      getBuffer(key) {
        return this._toneGenerator.getBuffer(key);
      }
      _getKey() {
        return this._toneGenerator.getKey(this._tone, this._frequency);
      }
      _dispatchBufferChanged() {
        if (this._active && this.bufferChanged.hasHandlers) {
          this.bufferChanged.dispatch(this._getKey());
        }
      }
    };
    exports.default = WaveformAudio;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/PCMChannel.js
var require_PCMChannel = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/PCMChannel.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var PCMChannel = class {
      constructor() {
        this._audv = 0;
        this._audc = 0;
        this._audf = 0;
        this._clkEnable = false;
        this._noiseFeedback = false;
        this._noiseCounterBit4 = false;
        this._pulseCounterHold = false;
        this._divCounter = 0;
        this._noiseCounter = 0;
        this._pulseCounter = 0;
        this.reset();
      }
      reset() {
        this._audc = this._audf = this._audv = 0;
        this._clkEnable = false;
        this._noiseFeedback = false;
        this._noiseCounterBit4 = false;
        this._pulseCounterHold = false;
        this._divCounter = 0;
        this._noiseCounter = 0;
        this._pulseCounter = 0;
      }
      phase0() {
        if (this._clkEnable) {
          this._noiseCounterBit4 = !!(this._noiseCounter & 1);
          switch (this._audc & 3) {
            case 0:
            case 1:
              this._pulseCounterHold = false;
              break;
            case 2:
              this._pulseCounterHold = (this._noiseCounter & 30) !== 2;
              break;
            case 3:
              this._pulseCounterHold = !this._noiseCounterBit4;
              break;
          }
          switch (this._audc & 3) {
            case 0:
              this._noiseFeedback = !!((this._pulseCounter ^ this._noiseCounter) & 1) || !(this._noiseCounter !== 0 || this._pulseCounter !== 10) || !(this._audc & 12);
              break;
            default:
              this._noiseFeedback = !!((this._noiseCounter & 4 ? 1 : 0) ^ this._noiseCounter & 1) || this._noiseCounter === 0;
              break;
          }
        }
        this._clkEnable = this._divCounter === this._audf;
        if (this._divCounter === this._audf || this._divCounter === 31) {
          this._divCounter = 0;
        } else {
          this._divCounter++;
        }
      }
      phase1() {
        let pulseFeedback = false;
        if (this._clkEnable) {
          switch (this._audc >>> 2) {
            case 0:
              pulseFeedback = !!((this._pulseCounter & 2 ? 1 : 0) ^ this._pulseCounter & 1) && this._pulseCounter !== 10 && !!(this._audc & 3);
              break;
            case 1:
              pulseFeedback = !(this._pulseCounter & 8);
              break;
            case 2:
              pulseFeedback = !this._noiseCounterBit4;
              break;
            case 3:
              pulseFeedback = !(!!(this._pulseCounter & 2) || !(this._pulseCounter & 14));
              break;
          }
          this._noiseCounter >>>= 1;
          if (this._noiseFeedback) {
            this._noiseCounter |= 16;
          }
          if (!this._pulseCounterHold) {
            this._pulseCounter = ~(this._pulseCounter >>> 1) & 7;
            if (pulseFeedback) {
              this._pulseCounter |= 8;
            }
          }
        }
        return (this._pulseCounter & 1) * this._audv;
      }
      audc(value) {
        this._audc = value & 15;
      }
      audf(value) {
        this._audf = value & 31;
      }
      audv(value) {
        this._audv = value & 15;
      }
    };
    exports.default = PCMChannel;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/PCMAudio.js
var require_PCMAudio = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/PCMAudio.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = exports.__init = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var PCMChannel_1 = tslib_1.__importDefault(require_PCMChannel());
    var R_MAX = 30;
    var R = 1;
    var VOL_MAX = 30;
    var mixingTable = new Float32Array(VOL_MAX + 1);
    var __init;
    (function(__init2) {
      for (let vol = 0; vol <= VOL_MAX; vol++) {
        mixingTable[vol] = vol / VOL_MAX * (R_MAX + R * VOL_MAX) / (R_MAX + R * vol);
      }
    })(__init = exports.__init || (exports.__init = {}));
    var PCMAudio = class {
      constructor(_config) {
        this._config = _config;
        this.newFrame = new microevent_ts_1.Event();
        this.togglePause = new microevent_ts_1.Event();
        this._currentOutputBuffer = null;
        this._bufferIndex = 0;
        this._sampleRate = 0;
        this._counter = 0;
        this._isActive = false;
        this._channel0 = new PCMChannel_1.default();
        this._channel1 = new PCMChannel_1.default();
        this._sampleRate = (this._config.tvMode === 0 ? 60 * 262 : 50 * 312) * 2;
        this._frameSize = (this._config.tvMode === 0 ? 262 : 312) * 4;
        this.reset();
      }
      getChannels() {
        return [
          {
            audv: (value) => this._channel0.audv(value),
            audc: (value) => this._channel0.audc(value),
            audf: (value) => this._channel0.audf(value),
            reset: () => this.reset(),
            setActive: (active) => this.setActive(active)
          },
          {
            audv: (value) => this._channel1.audv(value),
            audc: (value) => this._channel1.audc(value),
            audf: (value) => this._channel1.audf(value),
            reset: () => void 0,
            setActive: () => void 0
          }
        ];
      }
      reset() {
        this._bufferIndex = 0;
        this._counter = 0;
        this._channel0.reset();
        this._channel1.reset();
      }
      tick() {
        switch (this._counter) {
          case 9:
          case 81:
            this._channel0.phase0();
            this._channel1.phase0();
            break;
          case 37:
          case 149:
            this._currentOutputBuffer.getContent()[this._bufferIndex++] = mixingTable[this._channel0.phase1() + this._channel1.phase1()];
            if (this._bufferIndex === this._currentOutputBuffer.getLength()) {
              this._dispatchBuffer();
            }
            break;
        }
        if (++this._counter === 228) {
          this._counter = 0;
        }
      }
      isPaused() {
        return !this._isActive;
      }
      setActive(isActive) {
        if (isActive === this._isActive) {
          return;
        }
        this._isActive = isActive;
        this.togglePause.dispatch(!isActive);
      }
      getSampleRate() {
        return this._sampleRate;
      }
      getFrameSize() {
        return this._frameSize;
      }
      setFrameBufferFactory(factory) {
        this._bufferFactory = factory;
        if (!this._currentOutputBuffer && factory) {
          this._currentOutputBuffer = factory();
          this._bufferIndex = 0;
        }
      }
      _dispatchBuffer() {
        this.newFrame.dispatch(this._currentOutputBuffer);
        this._currentOutputBuffer = this._bufferFactory ? this._bufferFactory() : null;
        this._bufferIndex = 0;
      }
    };
    exports.default = PCMAudio;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/drawCounterDecodes.js
var require_drawCounterDecodes = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/drawCounterDecodes.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.decodesPlayer = exports.decodesMissile = void 0;
    var decodes0 = new Uint8Array(160);
    var decodes1 = new Uint8Array(160);
    var decodes2 = new Uint8Array(160);
    var decodes3 = new Uint8Array(160);
    var decodes4 = new Uint8Array(160);
    var decodes6 = new Uint8Array(160);
    exports.decodesMissile = [
      decodes0,
      decodes1,
      decodes2,
      decodes3,
      decodes4,
      decodes0,
      decodes6,
      decodes0
    ];
    exports.decodesPlayer = [
      decodes0,
      decodes1,
      decodes2,
      decodes3,
      decodes4,
      decodes0,
      decodes6,
      decodes0
    ];
    [decodes0, decodes1, decodes2, decodes3, decodes4, decodes6].forEach((decodes) => {
      for (let i = 0; i < 160; i++) {
        decodes[i] = 0;
      }
      decodes[156] = 1;
    });
    decodes1[12] = 1;
    decodes2[28] = 1;
    decodes3[12] = decodes3[28] = 1;
    decodes4[60] = 1;
    decodes6[28] = decodes6[60] = 1;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/Missile.js
var require_Missile = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/Missile.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var drawCounterDecodes_1 = require_drawCounterDecodes();
    var Missile = class {
      constructor(_collisionMask, _flushLineCache) {
        this._collisionMask = _collisionMask;
        this._flushLineCache = _flushLineCache;
        this.color = 4294967295;
        this.collision = 0;
        this._enabled = false;
        this._enam = false;
        this._resmp = -1;
        this._hmmClocks = 0;
        this._counter = 0;
        this._moving = false;
        this._width = 1;
        this._effectiveWidth = 0;
        this._lastMovementTick = 0;
        this._rendering = false;
        this._renderCounter = -4;
        this._widths = new Uint8Array([1, 2, 4, 8]);
        this.reset();
      }
      reset() {
        this.color = 4294967295;
        this._width = 1;
        this._enabled = false;
        this._counter = 0;
        this._rendering = false;
        this._renderCounter = -4;
        this._moving = false;
        this._hmmClocks = 0;
        this._decodes = drawCounterDecodes_1.decodesMissile[0];
        this._resmp = 0;
        this._enam = false;
        this._effectiveWidth = 0;
        this._lastMovementTick = 0;
      }
      enam(value) {
        const enam = (value & 2) > 0, enabled = enam && this._resmp === 0;
        if (enam !== this._enam || enabled !== this._enabled) {
          this._flushLineCache();
        }
        this._enam = enam;
        this._enabled = enabled;
      }
      hmm(value) {
        this._hmmClocks = value >>> 4 ^ 8;
      }
      resm(counter, hblank) {
        this._counter = counter;
        if (this._rendering) {
          if (this._renderCounter < 0) {
            this._renderCounter = -4 + (counter - 157);
          } else {
            switch (this._width) {
              case 8:
                this._renderCounter = counter - 157 + (this._renderCounter >= 4 ? 4 : 0);
                break;
              case 4:
                this._renderCounter = counter - 157;
                break;
              case 2:
                if (hblank) {
                  this._rendering = this._renderCounter > 1;
                } else if (this._renderCounter === 0) {
                  this._renderCounter++;
                }
                break;
              default:
                if (hblank) {
                  this._rendering = this._renderCounter > 0;
                }
                break;
            }
          }
        }
      }
      resmp(value, player) {
        const resmp = value & 2;
        if (resmp === this._resmp) {
          return;
        }
        this._flushLineCache();
        this._resmp = resmp;
        if (resmp) {
          this._enabled = false;
        } else {
          this._enabled = this._enam;
          this._counter = player.getRespClock();
        }
      }
      nusiz(value) {
        this._width = this._widths[(value & 48) >>> 4];
        this._decodes = drawCounterDecodes_1.decodesMissile[value & 7];
        if (this._rendering && this._renderCounter >= this._width) {
          this._rendering = false;
        }
      }
      startMovement() {
        this._moving = true;
      }
      movementTick(clock, apply) {
        this._lastMovementTick = this._counter;
        if (clock === this._hmmClocks) {
          this._moving = false;
        }
        if (this._moving && apply) {
          this.tick(false);
        }
        return this._moving;
      }
      tick(isReceivingHclock) {
        this.collision = this._rendering && this._renderCounter >= 0 && this._enabled ? 0 : this._collisionMask;
        const starfieldEffect = this._moving && isReceivingHclock;
        if (this._decodes[this._counter] && !this._resmp) {
          const starfieldDelta = (this._counter - this._lastMovementTick + 160) % 4;
          this._rendering = true;
          this._renderCounter = -4;
          if (starfieldEffect && starfieldDelta === 3 && this._width < 4) {
            this._renderCounter++;
          }
          switch (starfieldDelta) {
            case 3:
              this._effectiveWidth = this._width === 1 ? 2 : this._width;
              break;
            case 2:
              this._effectiveWidth = 0;
              break;
            default:
              this._effectiveWidth = this._width;
              break;
          }
        } else if (this._rendering && ++this._renderCounter >= (starfieldEffect ? this._effectiveWidth : this._width)) {
          this._rendering = false;
        }
        if (++this._counter >= 160) {
          this._counter = 0;
        }
      }
      getPixel(colorIn) {
        return this.collision ? colorIn : this.color;
      }
      setColor(color) {
        if (color !== this.color && this._enabled) {
          this._flushLineCache();
        }
        this.color = color;
      }
    };
    exports.default = Missile;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/Playfield.js
var require_Playfield = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/Playfield.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var Playfield = class {
      constructor(_collisionMask, _flushLineCache) {
        this._collisionMask = _collisionMask;
        this._flushLineCache = _flushLineCache;
        this.collision = 0;
        this._colorLeft = 0;
        this._colorRight = 0;
        this._color = 0;
        this._colorP0 = 0;
        this._colorP1 = 0;
        this._colorMode = 0;
        this._pattern = 0;
        this._refp = false;
        this._reflected = false;
        this._pf0 = 0;
        this._pf1 = 0;
        this._pf2 = 0;
        this._x = 0;
        this.reset();
      }
      reset() {
        this._pattern = 0;
        this._reflected = false;
        this._refp = false;
        this._pf0 = 0;
        this._pf1 = 0;
        this._pf2 = 0;
        this._color = 0;
        this._colorP0 = 0;
        this._colorP1 = 0;
        this._colorMode = 0;
        this._applyColors();
      }
      pf0(value) {
        if (this._pf0 === value >>> 4) {
          return;
        }
        this._flushLineCache();
        this._pf0 = value >>> 4;
        this._pattern = this._pattern & 1048560 | this._pf0;
      }
      pf1(value) {
        if (this._pf1 === value) {
          return;
        }
        this._flushLineCache();
        this._pf1 = value;
        this._pattern = this._pattern & 1044495 | (value & 128) >>> 3 | (value & 64) >>> 1 | (value & 32) << 1 | (value & 16) << 3 | (value & 8) << 5 | (value & 4) << 7 | (value & 2) << 9 | (value & 1) << 11;
      }
      pf2(value) {
        if (this._pf2 === value) {
          return;
        }
        this._flushLineCache();
        this._pf2 = value;
        this._pattern = this._pattern & 4095 | (value & 255) << 12;
      }
      ctrlpf(value) {
        const reflected = (value & 1) > 0, colorMode = (value & 6) === 2 ? 1 : 0;
        if (reflected === this._reflected && colorMode === this._colorMode) {
          return;
        }
        this._flushLineCache();
        this._reflected = reflected;
        this._colorMode = colorMode;
        this._applyColors();
      }
      setColor(color) {
        if (color !== this._color && this._colorMode === 0) {
          this._flushLineCache();
        }
        this._color = color;
        this._applyColors();
      }
      setColorP0(color) {
        if (color !== this._colorP0 && this._colorMode === 1) {
          this._flushLineCache();
        }
        this._colorP0 = color;
        this._applyColors();
      }
      setColorP1(color) {
        if (color !== this._colorP1 && this._colorMode === 1) {
          this._flushLineCache();
        }
        this._colorP1 = color;
        this._applyColors();
      }
      tick(x) {
        this._x = x;
        if (x === 80 || x === 0) {
          this._refp = this._reflected;
        }
        if (x & 3) {
          return;
        }
        let currentPixel;
        if (this._pattern === 0) {
          currentPixel = 0;
        } else if (x < 80) {
          currentPixel = this._pattern & 1 << (x >>> 2);
        } else if (this._refp) {
          currentPixel = this._pattern & 1 << 39 - (x >>> 2);
        } else {
          currentPixel = this._pattern & 1 << (x >>> 2) - 20;
        }
        this.collision = currentPixel ? 0 : this._collisionMask;
      }
      getPixel(colorIn) {
        if (!this.collision) {
          return this._x < 80 ? this._colorLeft : this._colorRight;
        }
        return colorIn;
      }
      _applyColors() {
        switch (this._colorMode) {
          case 0:
            this._colorLeft = this._colorRight = this._color;
            break;
          case 1:
            this._colorLeft = this._colorP0;
            this._colorRight = this._colorP1;
            break;
        }
      }
    };
    exports.default = Playfield;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/Player.js
var require_Player = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/Player.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var drawCounterDecodes_1 = require_drawCounterDecodes();
    var Player = class {
      constructor(_collisionMask, _flushLineCache) {
        this._collisionMask = _collisionMask;
        this._flushLineCache = _flushLineCache;
        this.color = 4294967295;
        this.collision = 0;
        this._hmmClocks = 0;
        this._counter = 0;
        this._moving = false;
        this._divider = 1;
        this._dividerPending = 1;
        this._dividerChangeCounter = -1;
        this._sampleCounter = 0;
        this._rendering = false;
        this._renderCounter = -5;
        this._renderCounterTripPoint = 0;
        this._patternNew = 0;
        this._patternOld = 0;
        this._pattern = 0;
        this._reflected = false;
        this._delaying = false;
        this.reset();
      }
      reset() {
        this.color = 4294967295;
        this.collision = 0;
        this._hmmClocks = 0;
        this._counter = 0;
        this._moving = false;
        this._rendering = false;
        this._renderCounter = -5;
        this._decodes = drawCounterDecodes_1.decodesPlayer[0];
        this._patternNew = 0;
        this._patternOld = 0;
        this._pattern = 0;
        this._reflected = false;
        this._delaying = false;
        this._sampleCounter = 0;
        this._dividerPending = 0;
        this._dividerChangeCounter = -1;
        this._setDivider(1);
      }
      grp(pattern) {
        if (pattern === this._patternNew) {
          return;
        }
        this._patternNew = pattern;
        if (!this._delaying) {
          this._flushLineCache();
          this._updatePattern();
        }
      }
      hmp(value) {
        this._hmmClocks = value >>> 4 ^ 8;
      }
      nusiz(value, hblank) {
        const masked = value & 7;
        switch (masked) {
          case 5:
            this._dividerPending = 2;
            break;
          case 7:
            this._dividerPending = 4;
            break;
          default:
            this._dividerPending = 1;
        }
        const oldDecodes = this._decodes;
        this._decodes = drawCounterDecodes_1.decodesPlayer[masked];
        if (this._decodes !== oldDecodes && this._rendering && this._renderCounter - -5 < 2 && !this._decodes[(this._counter - this._renderCounter + -5 + 159) % 160]) {
          this._rendering = false;
        }
        if (this._dividerPending === this._divider) {
          return;
        }
        if (!this._rendering) {
          this._setDivider(this._dividerPending);
          return;
        }
        const delta = this._renderCounter - -5;
        switch (this._divider << 4 | this._dividerPending) {
          case 18:
          case 20:
            if (hblank) {
              if (delta < 4) {
                this._setDivider(this._dividerPending);
              } else {
                this._dividerChangeCounter = delta < 5 ? 1 : 0;
              }
            } else {
              if (delta < 3) {
                this._setDivider(this._dividerPending);
              } else {
                this._dividerChangeCounter = 1;
              }
            }
            break;
          case 33:
          case 65:
            if (delta < (hblank ? 4 : 3)) {
              this._setDivider(this._dividerPending);
            } else if (delta < (hblank ? 6 : 5)) {
              this._setDivider(this._dividerPending);
              this._renderCounter--;
            } else {
              this._dividerChangeCounter = hblank ? 0 : 1;
            }
            break;
          case 66:
          case 36:
            if (this._renderCounter < 1 || hblank && this._renderCounter % this._divider === 1) {
              this._setDivider(this._dividerPending);
            } else {
              this._dividerChangeCounter = this._divider - (this._renderCounter - 1) % this._divider;
            }
            break;
          default:
            throw new Error("cannot happen");
        }
      }
      resp(counter) {
        this._counter = counter;
        if (this._rendering && this._renderCounter - -5 < 4) {
          this._renderCounter = -5 + (counter - 157);
        }
      }
      refp(value) {
        const oldReflected = this._reflected;
        this._reflected = (value & 8) > 0;
        if (this._reflected !== oldReflected) {
          this._flushLineCache();
          this._updatePattern();
        }
      }
      vdelp(value) {
        const oldDelaying = this._delaying;
        this._delaying = (value & 1) > 0;
        if (this._delaying !== oldDelaying) {
          this._flushLineCache();
          this._updatePattern();
        }
      }
      startMovement() {
        this._moving = true;
      }
      movementTick(clock, apply) {
        if (clock === this._hmmClocks) {
          this._moving = false;
        }
        if (this._moving && apply) {
          this.tick();
        }
        return this._moving;
      }
      tick() {
        this.collision = this._rendering && this._renderCounter >= this._renderCounterTripPoint && this._pattern & 1 << this._sampleCounter ? 0 : this._collisionMask;
        if (this._decodes[this._counter]) {
          this._rendering = true;
          this._renderCounter = -5;
          this._sampleCounter = 0;
        } else if (this._rendering) {
          this._renderCounter++;
          switch (this._divider) {
            case 1:
              if (this._renderCounter > 0) {
                this._sampleCounter++;
              }
              if (this._renderCounter >= 0 && this._dividerChangeCounter >= 0 && this._dividerChangeCounter-- === 0) {
                this._setDivider(this._dividerPending);
              }
              break;
            default:
              if (this._renderCounter > 1 && (this._renderCounter - 1) % this._divider === 0) {
                this._sampleCounter++;
              }
              if (this._renderCounter > 0 && this._dividerChangeCounter >= 0 && this._dividerChangeCounter-- === 0) {
                this._setDivider(this._dividerPending);
              }
              break;
          }
          if (this._sampleCounter > 7) {
            this._rendering = false;
          }
        }
        if (++this._counter >= 160) {
          this._counter = 0;
        }
      }
      getPixel(colorIn) {
        return this.collision ? colorIn : this.color;
      }
      shufflePatterns() {
        const oldPatternOld = this._patternOld;
        this._patternOld = this._patternNew;
        if (this._delaying && oldPatternOld !== this._patternOld) {
          this._flushLineCache();
          this._updatePattern();
        }
      }
      getRespClock() {
        switch (this._divider) {
          case 1:
            return (this._counter - 5 + 160) % 160;
          case 2:
            return (this._counter - 9 + 160) % 160;
          case 4:
            return (this._counter - 12 + 160) % 160;
          default:
            throw new Error(`cannot happen: invalid divider ${this._divider}`);
        }
      }
      setColor(color) {
        if (color !== this.color && this._pattern) {
          this._flushLineCache();
        }
        this.color = color;
      }
      _updatePattern() {
        this._pattern = this._delaying ? this._patternOld : this._patternNew;
        if (!this._reflected) {
          this._pattern = (this._pattern & 1) << 7 | (this._pattern & 2) << 5 | (this._pattern & 4) << 3 | (this._pattern & 8) << 1 | (this._pattern & 16) >>> 1 | (this._pattern & 32) >>> 3 | (this._pattern & 64) >>> 5 | (this._pattern & 128) >>> 7;
        }
      }
      _setDivider(divider) {
        this._divider = divider;
        this._renderCounterTripPoint = divider === 1 ? 0 : 1;
      }
    };
    exports.default = Player;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/Ball.js
var require_Ball = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/Ball.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var Ball = class {
      constructor(_collisionMask, _flushLineCache) {
        this._collisionMask = _collisionMask;
        this._flushLineCache = _flushLineCache;
        this.color = 4294967295;
        this.collision = 0;
        this._enabledOld = false;
        this._enabledNew = false;
        this._enabled = false;
        this._hmmClocks = 0;
        this._counter = 0;
        this._moving = false;
        this._width = 1;
        this._effectiveWidth = 0;
        this._lastMovementTick = 0;
        this._rendering = false;
        this._renderCounter = -4;
        this._widths = new Uint8Array([1, 2, 4, 8]);
        this._delaying = false;
        this.reset();
      }
      reset() {
        this.color = 4294967295;
        this.collision = 0;
        this._width = 1;
        this._enabledOld = false;
        this._enabledNew = false;
        this._enabled = false;
        this._counter = 0;
        this._rendering = false;
        this._renderCounter = -4;
        this._moving = false;
        this._hmmClocks = 0;
        this._delaying = false;
        this._effectiveWidth = 0;
        this._lastMovementTick = 0;
      }
      enabl(value) {
        const enabledNewOldValue = this._enabledNew;
        this._enabledNew = (value & 2) > 0;
        if (enabledNewOldValue !== this._enabledNew && !this._delaying) {
          this._flushLineCache();
          this._updateEnabled();
        }
      }
      hmbl(value) {
        this._hmmClocks = value >>> 4 ^ 8;
      }
      resbl(counter) {
        this._counter = counter;
        this._rendering = true;
        this._renderCounter = -4 + (counter - 157);
      }
      ctrlpf(value) {
        const width = this._widths[(value & 48) >>> 4];
        if (width !== this._width) {
          this._flushLineCache();
        }
        this._width = width;
      }
      vdelbl(value) {
        const oldDelaying = this._delaying;
        this._delaying = (value & 1) > 0;
        if (oldDelaying !== this._delaying) {
          this._flushLineCache();
          this._updateEnabled();
        }
      }
      startMovement() {
        this._moving = true;
      }
      movementTick(clock, apply) {
        this._lastMovementTick = this._counter;
        if (clock === this._hmmClocks) {
          this._moving = false;
        }
        if (this._moving && apply) {
          this.tick(false);
        }
        return this._moving;
      }
      tick(isReceivingHclock) {
        this.collision = this._rendering && this._renderCounter >= 0 && this._enabled ? 0 : this._collisionMask;
        const starfieldEffect = this._moving && isReceivingHclock;
        if (this._counter === 156) {
          const starfieldDelta = (this._counter - this._lastMovementTick + 160) % 4;
          this._rendering = true;
          this._renderCounter = -4;
          if (starfieldEffect && starfieldDelta === 3 && this._width < 4) {
            this._renderCounter++;
          }
          switch (starfieldDelta) {
            case 3:
              this._effectiveWidth = this._width === 1 ? 2 : this._width;
              break;
            case 2:
              this._effectiveWidth = 0;
              break;
            default:
              this._effectiveWidth = this._width;
              break;
          }
        } else if (this._rendering && ++this._renderCounter >= (starfieldEffect ? this._effectiveWidth : this._width)) {
          this._rendering = false;
        }
        if (++this._counter >= 160) {
          this._counter = 0;
        }
      }
      getPixel(colorIn) {
        return this.collision ? colorIn : this.color;
      }
      shuffleStatus() {
        const oldEnabledOld = this._enabledOld;
        this._enabledOld = this._enabledNew;
        if (this._delaying && this._enabledOld !== oldEnabledOld) {
          this._flushLineCache();
          this._updateEnabled();
        }
      }
      setColor(color) {
        if (color !== this.color && this._enabled) {
          this._flushLineCache();
        }
        this.color = color;
      }
      _updateEnabled() {
        this._enabled = this._delaying ? this._enabledOld : this._enabledNew;
      }
    };
    exports.default = Ball;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/LatchedInput.js
var require_LatchedInput = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/LatchedInput.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var LatchedInput = class {
      constructor(_switch) {
        this._switch = _switch;
        this._modeLatched = false;
        this._latchedValue = 0;
        this.reset();
      }
      reset() {
        this._modeLatched = false;
        this._latchedValue = 0;
      }
      vblank(value) {
        if (value & 64) {
          this._modeLatched = true;
        } else {
          this._modeLatched = false;
          this._latchedValue = 128;
        }
      }
      inpt() {
        let value = this._switch.read() ? 0 : 128;
        if (this._modeLatched) {
          this._latchedValue &= value;
          value = this._latchedValue;
        }
        return value;
      }
    };
    exports.default = LatchedInput;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/PaddleReader.js
var require_PaddleReader = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/PaddleReader.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var C = 68e-9;
    var RPOT = 1e6;
    var R0 = 1800;
    var U = 5;
    var LINES_FULL = 380;
    var PaddleReader = class {
      constructor(clockFreq, _paddle) {
        this._paddle = _paddle;
        this._uThresh = 0;
        this._u = 0;
        this._dumped = false;
        this._value = 0.5;
        this._timestamp = 0;
        this._cpuTimeProvider = null;
        this._uThresh = U * (1 - Math.exp(-LINES_FULL * 228 / clockFreq / (RPOT + R0) / C));
        this._paddle.valueChanged.addHandler((value) => {
          this._updateValue();
          this._value = value;
        });
        this.reset();
      }
      setCpuTimeProvider(provider) {
        this._cpuTimeProvider = provider;
        this._timestamp = this._cpuTimeProvider();
      }
      reset() {
        this._u = 0;
        this._value = this._paddle.getValue();
        this._dumped = false;
        this._timestamp = this._cpuTimeProvider ? this._cpuTimeProvider() : 0;
      }
      vblank(value) {
        const oldValue = this._dumped;
        if (value & 128) {
          this._dumped = true;
          this._u = 0;
        } else if (oldValue) {
          this._dumped = false;
          this._timestamp = this._cpuTimeProvider();
        }
      }
      inpt() {
        this._updateValue();
        const state = this._dumped ? false : this._u >= this._uThresh;
        return state ? 128 : 0;
      }
      _updateValue() {
        if (this._dumped) {
          return;
        }
        const timestamp = this._cpuTimeProvider();
        this._u = U * (1 - (1 - this._u / U) * Math.exp(-(timestamp - this._timestamp) / (this._value * RPOT + R0) / C));
        this._timestamp = timestamp;
      }
    };
    exports.default = PaddleReader;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/FrameManager.js
var require_FrameManager = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/FrameManager.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var microevent_ts_1 = require_lib();
    var FrameManager = class {
      constructor(_config) {
        this._config = _config;
        this.newFrame = new microevent_ts_1.Event();
        this.vblank = false;
        this.surfaceBuffer = null;
        this._vblankLines = 0;
        this._kernelLines = 0;
        this._overscanLines = 0;
        this._linesWithoutVsync = 0;
        this._state = 0;
        this._vsync = false;
        this._lineInState = 0;
        this._surfaceFactory = null;
        this._surface = null;
        this._frameStart = -1;
        switch (this._config.tvMode) {
          case 0:
            this._vblankLines = 40;
            this._kernelLines = 192;
            this._overscanLines = 30;
            break;
          case 1:
          case 2:
            this._vblankLines = 48;
            this._kernelLines = 228;
            this._overscanLines = 36;
            break;
          default:
            throw new Error(`invalid tv mode ${this._config.tvMode}`);
        }
        this._frameStart = this._config.frameStart;
        this.reset();
      }
      reset() {
        this.vblank = false;
        this.surfaceBuffer = null;
        this._linesWithoutVsync = 0;
        this._state = 0;
        this._vsync = false;
        this._lineInState = 0;
        this._surface = null;
      }
      nextLine() {
        if (!this._surfaceFactory) {
          return;
        }
        this._lineInState++;
        switch (this._state) {
          case 0:
          case 1:
            if (++this._linesWithoutVsync > 150) {
              this._setState(2);
            }
            break;
          case 2:
            if (this._frameStart >= 0) {
              if (this._lineInState > this._frameStart) {
                this._startFrame();
              }
            } else {
              if (this._lineInState >= (this.vblank ? this._vblankLines : this._vblankLines - 10)) {
                this._startFrame();
              }
            }
            break;
          case 3:
            if (this._lineInState >= this._kernelLines + 20) {
              this._finalizeFrame();
            }
            break;
          case 4:
            if (this._lineInState >= this._overscanLines - 20) {
              this._setState(0);
            }
            break;
        }
      }
      isRendering() {
        return this._state === 3 && !!this._surface;
      }
      setVblank(vblank) {
        if (this._surfaceFactory) {
          this.vblank = vblank;
        }
      }
      setVsync(vsync) {
        if (!this._surfaceFactory || vsync === this._vsync) {
          return;
        }
        this._vsync = vsync;
        switch (this._state) {
          case 0:
            this._linesWithoutVsync = 0;
          case 2:
          case 4:
            if (vsync) {
              this._setState(1);
            }
            break;
          case 1:
            if (!vsync) {
              this._setState(2);
            }
            break;
          case 3:
            if (vsync) {
              this._finalizeFrame();
            }
            break;
        }
      }
      getHeight() {
        return this._kernelLines + 20;
      }
      setSurfaceFactory(factory) {
        this._surfaceFactory = factory;
      }
      getCurrentLine() {
        return this._state === 3 ? this._lineInState : 0;
      }
      getDebugState() {
        return `${this._getReadableState()}, line = ${this._lineInState}, vblank = ${this.vblank ? "1" : "0"}`;
      }
      _getReadableState() {
        switch (this._state) {
          case 0:
            return `wait for vsync start`;
          case 1:
            return `wait for vsync end`;
          case 2:
            return `wait for frame start`;
          case 3:
            return `frame`;
          case 4:
            return `overscan`;
        }
      }
      _startFrame() {
        this._setState(3);
        this._surface = this._surfaceFactory();
        this.surfaceBuffer = this._surface.getBuffer();
      }
      _finalizeFrame() {
        if (this._state !== 3) {
          throw new Error(`finalize frame in invalid state ${this._state}`);
        }
        this.newFrame.dispatch(this._surface);
        this._setState(4);
      }
      _setState(newState) {
        this._state = newState;
        this._lineInState = 0;
      }
    };
    exports.default = FrameManager;
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/DelayQueue.js
var require_DelayQueue = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/DelayQueue.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var DelayQueue = class {
      constructor(_length, size) {
        this._length = _length;
        this._nextIndex = 0;
        this._indices = new Uint8Array(255);
        this._queue = new Array(this._length);
        for (let i = 0; i < this._length; i++) {
          this._queue[i] = new QueueEntry(size);
        }
      }
      reset() {
        for (let i = 0; i < this._length; i++) {
          this._queue[i].nextIndex = 0;
        }
      }
      push(address, value, delay) {
        if (delay >= this._length) {
          throw new Error("delay exceeds queue length");
        }
        const currentIndex = this._indices[address];
        if (currentIndex < this._length) {
          this._queue[currentIndex].remove(address);
        }
        const index = (this._nextIndex + delay) % this._length;
        this._queue[index].push(address, value);
        this._indices[address] = index;
        return this;
      }
      execute(handler, scope) {
        const entry = this._queue[this._nextIndex];
        this._nextIndex = (this._nextIndex + 1) % this._length;
        for (let i = 0; i < entry.nextIndex; i++) {
          handler(entry.addresses[i], entry.values[i], scope);
          this._indices[entry.addresses[i]] = 255;
        }
        entry.nextIndex = 0;
      }
    };
    exports.default = DelayQueue;
    var QueueEntry = class {
      constructor(size) {
        this.size = size;
        this.nextIndex = 0;
        this.addresses = new Uint8Array(size);
        this.values = new Uint8Array(size);
      }
      push(address, value) {
        if (this.nextIndex >= this.size) {
          throw new Error("delay queue overflow");
        }
        this.addresses[this.nextIndex] = address;
        this.values[this.nextIndex] = value;
        this.nextIndex++;
      }
      remove(address) {
        let i;
        for (i = 0; i < this.nextIndex; i++) {
          if (this.addresses[i] === address) {
            break;
          }
        }
        if (i < this.nextIndex) {
          this.addresses[i] = this.addresses[this.nextIndex - 1];
          this.values[i] = this.values[this.nextIndex - 1];
          this.nextIndex--;
        }
      }
    };
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/palette.js
var require_palette = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/palette.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.SECAM = exports.PAL = exports.NTSC = void 0;
    exports.NTSC = new Uint32Array([
      4278190080,
      4283058762,
      4285493103,
      4287532686,
      4289374890,
      4290822336,
      4292269782,
      4293717228,
      4278208584,
      4279200105,
      4280125062,
      4280984226,
      4281711547,
      4282438354,
      4283099368,
      4283759868,
      4278201468,
      4279322768,
      4280378018,
      4281367220,
      4282224835,
      4283081938,
      4283807711,
      4284532972,
      4278197392,
      4279581091,
      4280832949,
      4282019014,
      4283073237,
      4284061667,
      4284984048,
      4285840636,
      4278190228,
      4279900839,
      4281479864,
      4282927304,
      4284243158,
      4285493220,
      4286611696,
      4287664380,
      4284743812,
      4286192023,
      4287574184,
      4288825016,
      4289944006,
      4290997460,
      4291984608,
      4292906220,
      4286840912,
      4288289128,
      4289540221,
      4290791058,
      4291844516,
      4292897973,
      4293819589,
      4294741204,
      4287627284,
      4288879155,
      4290064974,
      4291184744,
      4292172927,
      4293095317,
      4293951657,
      4294742204,
      4287889408,
      4289141272,
      4290261549,
      4291315778,
      4292238420,
      4293160805,
      4293951605,
      4294742148,
      4287110144,
      4288494360,
      4289746733,
      4290933314,
      4291988052,
      4292976741,
      4293899637,
      4294756484,
      4284755968,
      4286599192,
      4288179501,
      4289759298,
      4291141716,
      4292458341,
      4293643381,
      4294762628,
      4281352192,
      4283327e3,
      4285104429,
      4286750274,
      4288264276,
      4289646949,
      4290963317,
      4292148356,
      4278207488,
      4279920154,
      4281500722,
      4282949704,
      4284267100,
      4285518447,
      4286638208,
      4287691920,
      4278205460,
      4279787317,
      4281171538,
      4282555502,
      4283742087,
      4284862622,
      4285917108,
      4286905544,
      4278204464,
      4279654736,
      4281038445,
      4282290824,
      4283411360,
      4284465847,
      4285454540,
      4286377184,
      4278201416,
      4279520617,
      4280707718,
      4281894562,
      4282884027,
      4283872978,
      4284730600,
      4285587708
    ]);
    exports.PAL = new Uint32Array([
      4278190080,
      4281019179,
      4283585106,
      4285953654,
      4288124823,
      4290164406,
      4292006610,
      4293717228,
      4278190080,
      4281019179,
      4283585106,
      4285953654,
      4288124823,
      4290164406,
      4292006610,
      4293717228,
      4278212736,
      4279923094,
      4281501611,
      4282948798,
      4284264399,
      4285513951,
      4286632430,
      4287684860,
      4278213700,
      4279925086,
      4281504630,
      4282952844,
      4284269216,
      4285519795,
      4286638788,
      4287691988,
      4278203504,
      4279914889,
      4281494432,
      4282942646,
      4284259017,
      4285509596,
      4286628588,
      4287681788,
      4279526400,
      4281696282,
      4283602994,
      4285444168,
      4287087964,
      4288600431,
      4290046848,
      4291361936,
      4279500912,
      4281670281,
      4283576992,
      4285417654,
      4287061193,
      4288573404,
      4290019564,
      4291334396,
      4284242944,
      4285953562,
      4287532594,
      4288980040,
      4290295900,
      4291545967,
      4292664448,
      4293717136,
      4284219504,
      4285799044,
      4287181462,
      4288563368,
      4289748151,
      4290867142,
      4291920083,
      4292907232,
      4285545472,
      4287191577,
      4288705839,
      4290154052,
      4291405143,
      4292655720,
      4293709433,
      4294762632,
      4285530200,
      4287175278,
      4288688771,
      4290136214,
      4291386535,
      4292636599,
      4293689542,
      4294742228,
      4285538304,
      4287184665,
      4288698927,
      4290147396,
      4291398487,
      4292649320,
      4293703033,
      4294756488,
      4286578740,
      4288027210,
      4289409631,
      4290660466,
      4291779715,
      4292833171,
      4293820578,
      4294742192,
      4287102976,
      4288485914,
      4289737266,
      4290922568,
      4291976284,
      4292964207,
      4293886080,
      4294742160,
      4278190080,
      4281019179,
      4283585106,
      4285953654,
      4288124823,
      4290164406,
      4292006610,
      4293717228,
      4278190080,
      4281019179,
      4283585106,
      4285953654,
      4288124823,
      4290164406,
      4292006610,
      4293717228
    ]);
    exports.SECAM = new Uint32Array([
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295,
      4278190080,
      4294910241,
      4286135536,
      4294922495,
      4278255487,
      4294967167,
      4282384383,
      4294967295
    ]);
  }
});

// node_modules/6502.ts/lib/machine/stella/tia/Tia.js
var require_Tia = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/tia/Tia.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var WaveformAudio_1 = tslib_1.__importDefault(require_WaveformAudio());
    var PCMAudio_1 = tslib_1.__importDefault(require_PCMAudio());
    var Missile_1 = tslib_1.__importDefault(require_Missile());
    var Playfield_1 = tslib_1.__importDefault(require_Playfield());
    var Player_1 = tslib_1.__importDefault(require_Player());
    var Ball_1 = tslib_1.__importDefault(require_Ball());
    var LatchedInput_1 = tslib_1.__importDefault(require_LatchedInput());
    var PaddleReader_1 = tslib_1.__importDefault(require_PaddleReader());
    var FrameManager_1 = tslib_1.__importDefault(require_FrameManager());
    var DelayQueue_1 = tslib_1.__importDefault(require_DelayQueue());
    var palette = tslib_1.__importStar(require_palette());
    var Tia = class _Tia {
      constructor(_config, joystick0, joystick1, paddles) {
        this._config = _config;
        this.newFrame = new microevent_ts_1.Event();
        this.trap = new microevent_ts_1.Event();
        this._cpu = null;
        this._bus = null;
        this._delayQueue = new DelayQueue_1.default(10, 20);
        this._hstate = 0;
        this._hctr = 0;
        this._collisionUpdateRequired = false;
        this._movementClock = 0;
        this._movementInProgress = false;
        this._extendedHblank = false;
        this._xDelta = 0;
        this._linesSinceChange = 0;
        this._maxLinesTotal = 0;
        this._colorBk = 4278190080;
        this._priority = 0;
        this._collisionMask = 0;
        this._player0 = new Player_1.default(31744, () => this._flushLineCache());
        this._player1 = new Player_1.default(17344, () => this._flushLineCache());
        this._missile0 = new Missile_1.default(8760, () => this._flushLineCache());
        this._missile1 = new Missile_1.default(4390, () => this._flushLineCache());
        this._playfield = new Playfield_1.default(1099, () => this._flushLineCache());
        this._ball = new Ball_1.default(2197, () => this._flushLineCache());
        this._waveformAudio = new Array(2);
        this._pcmAudio = null;
        this._audio = new Array(2);
        this._frameManager = new FrameManager_1.default(this._config);
        this._frameManager.newFrame.addHandler(_Tia._onNewFrame, this);
        this._palette = this._getPalette(this._config);
        this._input0 = new LatchedInput_1.default(joystick0.getFire());
        this._input1 = new LatchedInput_1.default(joystick1.getFire());
        this._pcmAudio = new PCMAudio_1.default(this._config);
        const pcmChannels = this._pcmAudio.getChannels();
        for (let i = 0; i < 2; i++) {
          this._waveformAudio[i] = new WaveformAudio_1.default(this._config);
          this._audio[i] = this._config.pcmAudio ? pcmChannels[i] : this._waveformAudio[i];
        }
        const clockFreq = this._getClockFreq(this._config);
        this._paddles = new Array(4);
        for (let i = 0; i < 4; i++) {
          this._paddles[i] = new PaddleReader_1.default(clockFreq, paddles[i]);
        }
        this.reset();
      }
      reset() {
        this._hctr = 0;
        this._movementInProgress = false;
        this._extendedHblank = false;
        this._movementClock = 0;
        this._priority = 0;
        this._hstate = 0;
        this._collisionMask = 0;
        this._colorBk = 4278190080;
        this._linesSinceChange = 0;
        this._collisionUpdateRequired = false;
        this._maxLinesTotal = 0;
        this._xDelta = 0;
        this._delayQueue.reset();
        this._frameManager.reset();
        this._missile0.reset();
        this._missile1.reset();
        this._player0.reset();
        this._player1.reset();
        this._playfield.reset();
        this._ball.reset();
        this._audio[0].reset();
        this._audio[1].reset();
        this._input0.reset();
        this._input1.reset();
        for (let i = 0; i < 4; i++) {
          this._paddles[i].reset();
        }
        if (this._cpu) {
          this._cpu.resume();
        }
      }
      setCpu(cpu) {
        this._cpu = cpu;
        return this;
      }
      setCpuTimeProvider(provider) {
        for (let i = 0; i < 4; i++) {
          this._paddles[i].setCpuTimeProvider(provider);
        }
        return this;
      }
      getWidth() {
        return 160;
      }
      getHeight() {
        return this._frameManager.getHeight();
      }
      setSurfaceFactory(factory) {
        this._frameManager.setSurfaceFactory(factory);
        return this;
      }
      getWaveformChannel(i) {
        return this._waveformAudio[i];
      }
      getPCMChannel() {
        return this._pcmAudio;
      }
      setAudioEnabled(state) {
        this._audio[0].setActive(state && this._config.enableAudio);
        this._audio[1].setActive(state && this._config.enableAudio);
      }
      read(address) {
        const lastDataBusValue = this._bus.getLastDataBusValue();
        let result;
        switch (address & 15) {
          case 8:
            result = (this._config.emulatePaddles ? this._paddles[0].inpt() : 0) | lastDataBusValue & 64;
            break;
          case 9:
            result = (this._config.emulatePaddles ? this._paddles[1].inpt() : 0) | lastDataBusValue & 64;
            break;
          case 10:
            result = (this._config.emulatePaddles ? this._paddles[2].inpt() : 0) | lastDataBusValue & 64;
            break;
          case 11:
            result = (this._config.emulatePaddles ? this._paddles[3].inpt() : 0) | lastDataBusValue & 64;
            break;
          case 12:
            result = this._input0.inpt() | lastDataBusValue & 64;
            break;
          case 13:
            result = this._input1.inpt() | lastDataBusValue & 64;
            break;
          case 0:
            result = (this._collisionMask & 8760 & 31744 ? 64 : 0) | (this._collisionMask & 8760 & 17344 ? 128 : 0);
            break;
          case 1:
            result = (this._collisionMask & 4390 & 17344 ? 64 : 0) | (this._collisionMask & 4390 & 31744 ? 128 : 0);
            break;
          case 2:
            result = (this._collisionMask & 31744 & 2197 ? 64 : 0) | (this._collisionMask & 31744 & 1099 ? 128 : 0);
            break;
          case 3:
            result = (this._collisionMask & 17344 & 2197 ? 64 : 0) | (this._collisionMask & 17344 & 1099 ? 128 : 0);
            break;
          case 4:
            result = (this._collisionMask & 8760 & 2197 ? 64 : 0) | (this._collisionMask & 8760 & 1099 ? 128 : 0);
            break;
          case 5:
            result = (this._collisionMask & 4390 & 2197 ? 64 : 0) | (this._collisionMask & 4390 & 1099 ? 128 : 0);
            break;
          case 7:
            result = (this._collisionMask & 8760 & 4390 ? 64 : 0) | (this._collisionMask & 31744 & 17344 ? 128 : 0);
            break;
          case 6:
            result = this._collisionMask & 2197 & 1099 ? 128 : 0;
            break;
          default:
            result = 0;
            break;
        }
        return result & 192 | lastDataBusValue & 63;
      }
      peek(address) {
        return this.read(address);
      }
      write(address, value) {
        let v = 0;
        switch (address & 63) {
          case 2:
            this._cpu.halt();
            break;
          case 3:
            this._flushLineCache();
            this._rsync();
            break;
          case 0:
            this._frameManager.setVsync((value & 2) > 0);
            break;
          case 1:
            this._input0.vblank(value);
            this._input1.vblank(value);
            for (let i = 0; i < 4; i++) {
              this._paddles[i].vblank(value);
            }
            this._delayQueue.push(1, value, 1);
            break;
          case 29:
            this._delayQueue.push(29, value, 1);
            break;
          case 30:
            this._delayQueue.push(30, value, 1);
            break;
          case 34:
            this._delayQueue.push(34, value, 2);
            break;
          case 35:
            this._delayQueue.push(35, value, 2);
            break;
          case 18:
            this._flushLineCache();
            this._missile0.resm(this._resxCounter(), this._hstate === 0);
            break;
          case 19:
            this._flushLineCache();
            this._missile1.resm(this._resxCounter(), this._hstate === 0);
            break;
          case 40:
            this._missile0.resmp(value, this._player0);
            break;
          case 41:
            this._missile1.resmp(value, this._player1);
            break;
          case 43:
            this._delayQueue.push(43, value, 2);
            break;
          case 4:
            this._flushLineCache();
            this._missile0.nusiz(value);
            this._player0.nusiz(value, this._hstate === 0);
            break;
          case 5:
            this._flushLineCache();
            this._missile1.nusiz(value);
            this._player1.nusiz(value, this._hstate === 0);
            break;
          case 42:
            this._delayQueue.push(42, value, 6);
            break;
          case 9:
            this._flushLineCache();
            this._colorBk = this._palette[(value & 255) >>> 1];
            break;
          case 6:
            v = this._palette[(value & 255) >>> 1];
            this._missile0.setColor(v);
            this._player0.setColor(v);
            this._playfield.setColorP0(v);
            break;
          case 7:
            v = this._palette[(value & 255) >>> 1];
            this._missile1.setColor(v);
            this._player1.setColor(v);
            this._playfield.setColorP1(v);
            break;
          case 13:
            this._delayQueue.push(13, value, 2);
            break;
          case 14:
            this._delayQueue.push(14, value, 2);
            break;
          case 15:
            this._delayQueue.push(15, value, 2);
            break;
          case 10:
            this._setPriority(value);
            this._playfield.ctrlpf(value);
            this._ball.ctrlpf(value);
            break;
          case 8:
            this._flushLineCache();
            v = this._palette[(value & 255) >>> 1];
            this._playfield.setColor(v);
            this._ball.color = v;
            break;
          case 27:
            this._delayQueue.push(27, value, 1).push(241, 0, 1);
            break;
          case 28:
            this._delayQueue.push(28, value, 1).push(240, 0, 1).push(242, 0, 1);
            break;
          case 16:
            this._flushLineCache();
            this._player0.resp(this._resxCounter());
            break;
          case 17:
            this._flushLineCache();
            this._player1.resp(this._resxCounter());
            break;
          case 11:
            this._delayQueue.push(11, value, 1);
            break;
          case 12:
            this._delayQueue.push(12, value, 1);
            break;
          case 32:
            this._delayQueue.push(32, value, 2);
            break;
          case 33:
            this._delayQueue.push(33, value, 2);
            break;
          case 37:
            this._player0.vdelp(value);
            break;
          case 38:
            this._player1.vdelp(value);
            break;
          case 31:
            this._delayQueue.push(31, value, 1);
            break;
          case 36:
            this._delayQueue.push(36, value, 2);
            break;
          case 20:
            this._flushLineCache();
            this._ball.resbl(this._resxCounter());
            break;
          case 39:
            this._ball.vdelbl(value);
            break;
          case 44:
            this._flushLineCache();
            this._collisionMask = 0;
            break;
          case 21:
            this._audio[0].audc(value);
            break;
          case 22:
            this._audio[1].audc(value);
            break;
          case 23:
            this._audio[0].audf(value);
            break;
          case 24:
            this._audio[1].audf(value);
            break;
          case 25:
            this._audio[0].audv(value);
            break;
          case 26:
            this._audio[1].audv(value);
            break;
        }
      }
      getDebugState() {
        return `hclock: ${this._hctr}   line: ${this._frameManager.getCurrentLine()}
` + this._frameManager.getDebugState();
      }
      setBus(bus) {
        this._bus = bus;
        return this;
      }
      cycle() {
        this._delayQueue.execute(_Tia._delayedWrite, this);
        this._collisionUpdateRequired = false;
        if (this._linesSinceChange < 2) {
          this._tickMovement();
          if (this._hstate === 0) {
            this._tickHblank();
          } else {
            this._tickHframe();
          }
          if (this._collisionUpdateRequired && !this._frameManager.vblank) {
            this._updateCollision();
          }
        } else {
          if (this._hctr === 0) {
            this._cpu.resume();
          }
        }
        if (++this._hctr >= 228) {
          this._nextLine();
        }
        if (this._config.pcmAudio) {
          this._pcmAudio.tick();
        }
      }
      static _delayedWrite(address, value, self2) {
        switch (address) {
          case 1:
            self2._flushLineCache();
            self2._frameManager.setVblank((value & 2) > 0);
            break;
          case 42:
            self2._flushLineCache();
            self2._movementClock = 0;
            self2._movementInProgress = true;
            if (!self2._extendedHblank) {
              self2._clearHmoveComb();
              self2._extendedHblank = true;
            }
            self2._missile0.startMovement();
            self2._missile1.startMovement();
            self2._player0.startMovement();
            self2._player1.startMovement();
            self2._ball.startMovement();
            break;
          case 13:
            self2._playfield.pf0(value);
            break;
          case 14:
            self2._playfield.pf1(value);
            break;
          case 15:
            self2._playfield.pf2(value);
            break;
          case 27:
            self2._player0.grp(value);
            break;
          case 28:
            self2._player1.grp(value);
            break;
          case 240:
            self2._player0.shufflePatterns();
            break;
          case 241:
            self2._player1.shufflePatterns();
            break;
          case 32:
            self2._player0.hmp(value);
            break;
          case 33:
            self2._player1.hmp(value);
            break;
          case 34:
            self2._missile0.hmm(value);
            break;
          case 35:
            self2._missile1.hmm(value);
            break;
          case 36:
            self2._ball.hmbl(value);
            break;
          case 43:
            self2._missile0.hmm(0);
            self2._missile1.hmm(0);
            self2._player0.hmp(0);
            self2._player1.hmp(0);
            self2._ball.hmbl(0);
            break;
          case 11:
            self2._player0.refp(value);
            break;
          case 12:
            self2._player1.refp(value);
            break;
          case 242:
            self2._ball.shuffleStatus();
            break;
          case 31:
            self2._ball.enabl(value);
            break;
          case 29:
            self2._missile0.enam(value);
            break;
          case 30:
            self2._missile1.enam(value);
            break;
        }
      }
      static _onNewFrame(surface, self2) {
        const linesTotal = self2._frameManager.getCurrentLine();
        if (linesTotal > self2._maxLinesTotal) {
          self2._maxLinesTotal = linesTotal;
        }
        if (linesTotal < self2._maxLinesTotal) {
          const buffer = surface.getBuffer(), base = 160 * linesTotal, boundary = self2._maxLinesTotal * 160;
          for (let i = base; i < boundary; i++) {
            buffer[i] = 4278190080;
          }
        }
        self2.newFrame.dispatch(surface);
      }
      _tickMovement() {
        if (!this._movementInProgress) {
          return;
        }
        if ((this._hctr & 3) === 0) {
          const apply = this._hstate === 0;
          let m = false;
          const movementCounter = this._movementClock > 15 ? 0 : this._movementClock;
          m = this._missile0.movementTick(movementCounter, apply) || m;
          m = this._missile1.movementTick(movementCounter, apply) || m;
          m = this._player0.movementTick(movementCounter, apply) || m;
          m = this._player1.movementTick(movementCounter, apply) || m;
          m = this._ball.movementTick(movementCounter, apply) || m;
          this._movementInProgress = m;
          this._collisionUpdateRequired = m;
          this._movementClock++;
        }
      }
      _tickHblank() {
        switch (this._hctr) {
          case 0:
            this._extendedHblank = false;
            this._cpu.resume();
            break;
          case 67:
            if (!this._extendedHblank) {
              this._hstate = 1;
            }
            break;
          case 75:
            if (this._extendedHblank) {
              this._hstate = 1;
            }
            break;
        }
        if (this._extendedHblank && this._hctr > 67) {
          this._playfield.tick(this._hctr - 68 + this._xDelta);
        }
      }
      _tickHframe() {
        const y = this._frameManager.getCurrentLine(), x = this._hctr - 68 + this._xDelta;
        this._collisionUpdateRequired = true;
        this._playfield.tick(x);
        this._tickSprites();
        if (this._frameManager.isRendering()) {
          this._renderPixel(x, y);
        }
      }
      _tickSprites() {
        this._missile0.tick(true);
        this._missile1.tick(true);
        this._player0.tick();
        this._player1.tick();
        this._ball.tick(true);
      }
      _nextLine() {
        if (this._linesSinceChange >= 2) {
          this._cloneLastLine();
        }
        this._hctr = 0;
        this._playfield.tick(0);
        if (!this._movementInProgress) {
          this._linesSinceChange++;
        }
        this._hstate = 0;
        this._xDelta = 0;
        this._frameManager.nextLine();
        if (this._frameManager.isRendering() && this._frameManager.getCurrentLine() === 0) {
          this._flushLineCache();
        }
      }
      _cloneLastLine() {
        const y = this._frameManager.getCurrentLine();
        if (!this._frameManager.isRendering() || y === 0) {
          return;
        }
        const delta = y * 160, prevDelta = (y - 1) * 160;
        for (let x = 0; x < 160; x++) {
          this._frameManager.surfaceBuffer[delta + x] = this._frameManager.surfaceBuffer[prevDelta + x];
        }
      }
      _getPalette(config) {
        switch (config.tvMode) {
          case 0:
            return palette.NTSC;
          case 1:
            return palette.PAL;
          case 2:
            return palette.SECAM;
          default:
            throw new Error("invalid TV mode");
        }
      }
      _getClockFreq(config) {
        return config.tvMode === 0 ? 60 * 228 * 262 : 50 * 228 * 312;
      }
      _renderPixel(x, y) {
        if (this._frameManager.vblank) {
          this._frameManager.surfaceBuffer[y * 160 + x] = 4278190080;
          return;
        }
        let color = this._colorBk;
        switch (this._priority) {
          case 0:
            color = this._playfield.getPixel(color);
            color = this._ball.getPixel(color);
            color = this._missile1.getPixel(color);
            color = this._player1.getPixel(color);
            color = this._missile0.getPixel(color);
            color = this._player0.getPixel(color);
            break;
          case 1:
            color = this._missile1.getPixel(color);
            color = this._player1.getPixel(color);
            color = this._missile0.getPixel(color);
            color = this._player0.getPixel(color);
            color = this._playfield.getPixel(color);
            color = this._ball.getPixel(color);
            break;
          case 2:
            color = this._ball.getPixel(color);
            color = this._missile1.getPixel(color);
            color = this._player1.getPixel(color);
            color = this._playfield.getPixel(color);
            color = this._missile0.getPixel(color);
            color = this._player0.getPixel(color);
            break;
          default:
            throw new Error("invalid priority");
        }
        this._frameManager.surfaceBuffer[y * 160 + x] = color;
      }
      _updateCollision() {
        this._collisionMask |= ~this._player0.collision & ~this._player1.collision & ~this._missile0.collision & ~this._missile1.collision & ~this._ball.collision & ~this._playfield.collision;
      }
      _clearHmoveComb() {
        if (this._frameManager.isRendering() && this._hstate === 0) {
          const offset = this._frameManager.getCurrentLine() * 160;
          for (let i = 0; i < 8; i++) {
            this._frameManager.surfaceBuffer[offset + i] = 4278190080;
          }
        }
      }
      _resxCounter() {
        return this._hstate === 0 ? this._hctr >= 73 ? 158 : 159 : 157;
      }
      _rsync() {
        const x = this._hctr > 68 ? this._hctr - 68 : 0;
        this._xDelta = 157 - x;
        if (this._frameManager.isRendering()) {
          const y = this._frameManager.getCurrentLine(), base = y * 160 + x, boundary = base + (y + 1) * 160;
          for (let i = base; i < boundary; i++) {
            this._frameManager.surfaceBuffer[i] = 4278190080;
          }
        }
        this._hctr = 225;
      }
      _setPriority(value) {
        const priority = value & 4 ? 1 : value & 2 ? 2 : 0;
        if (priority !== this._priority) {
          this._flushLineCache();
          this._priority = priority;
        }
      }
      _flushLineCache() {
        const wasCaching = this._linesSinceChange >= 2;
        this._linesSinceChange = 0;
        if (wasCaching) {
          const rewindCycles = this._hctr;
          for (this._hctr = 0; this._hctr < rewindCycles; this._hctr++) {
            if (this._hstate === 0) {
              this._tickHblank();
            } else {
              this._tickHframe();
            }
          }
        }
      }
    };
    exports.default = Tia;
    (function(Tia2) {
      class TrapPayload {
        constructor(reason, tia, message) {
          this.reason = reason;
          this.tia = tia;
          this.message = message;
        }
      }
      Tia2.TrapPayload = TrapPayload;
    })(Tia || (Tia = {}));
    exports.default = Tia;
  }
});

// node_modules/6502.ts/lib/machine/io/Switch.js
var require_Switch = __commonJS({
  "node_modules/6502.ts/lib/machine/io/Switch.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var microevent_ts_1 = require_lib();
    var Switch = class {
      constructor(_state = false) {
        this._state = _state;
        this.stateChanged = new microevent_ts_1.Event();
        this.beforeRead = new microevent_ts_1.Event();
      }
      read() {
        this.beforeRead.dispatch(this);
        return this._state;
      }
      peek() {
        return this._state;
      }
      toggle(state) {
        if (this._state === state) {
          return;
        }
        this._state = state;
        this.stateChanged.dispatch(state);
      }
    };
    exports.default = Switch;
  }
});

// node_modules/6502.ts/lib/machine/stella/ControlPanel.js
var require_ControlPanel = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/ControlPanel.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Switch_1 = tslib_1.__importDefault(require_Switch());
    var ControlPanel = class {
      constructor() {
        this._selectSwitch = new Switch_1.default();
        this._resetButton = new Switch_1.default();
        this._colorSwitch = new Switch_1.default();
        this._difficutlyP0 = new Switch_1.default();
        this._difficutlyP1 = new Switch_1.default();
      }
      getSelectSwitch() {
        return this._selectSwitch;
      }
      getResetButton() {
        return this._resetButton;
      }
      getColorSwitch() {
        return this._colorSwitch;
      }
      getDifficultySwitchP0() {
        return this._difficutlyP0;
      }
      getDifficultySwitchP1() {
        return this._difficutlyP1;
      }
    };
    exports.default = ControlPanel;
  }
});

// node_modules/6502.ts/lib/machine/io/DigitalJoystick.js
var require_DigitalJoystick = __commonJS({
  "node_modules/6502.ts/lib/machine/io/DigitalJoystick.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var Switch_1 = tslib_1.__importDefault(require_Switch());
    var DigitalJoystick = class {
      constructor() {
        this._left = new Switch_1.default();
        this._right = new Switch_1.default();
        this._up = new Switch_1.default();
        this._down = new Switch_1.default();
        this._fire = new Switch_1.default();
      }
      getLeft() {
        return this._left;
      }
      getRight() {
        return this._right;
      }
      getUp() {
        return this._up;
      }
      getDown() {
        return this._down;
      }
      getFire() {
        return this._fire;
      }
    };
    exports.default = DigitalJoystick;
  }
});

// node_modules/6502.ts/lib/machine/io/Paddle.js
var require_Paddle = __commonJS({
  "node_modules/6502.ts/lib/machine/io/Paddle.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var Switch_1 = tslib_1.__importDefault(require_Switch());
    var Paddle = class {
      constructor() {
        this.valueChanged = new microevent_ts_1.Event();
        this._fireSwitch = new Switch_1.default();
        this._value = 0.5;
      }
      setValue(value) {
        this._value = value;
        this.valueChanged.dispatch(value);
      }
      getValue() {
        return this._value;
      }
      getFire() {
        return this._fireSwitch;
      }
    };
    exports.default = Paddle;
  }
});

// node_modules/seedrandom/lib/alea.js
var require_alea = __commonJS({
  "node_modules/seedrandom/lib/alea.js"(exports, module) {
    (function(global, module2, define2) {
      function Alea(seed) {
        var me = this, mash = Mash();
        me.next = function() {
          var t = 2091639 * me.s0 + me.c * 23283064365386963e-26;
          me.s0 = me.s1;
          me.s1 = me.s2;
          return me.s2 = t - (me.c = t | 0);
        };
        me.c = 1;
        me.s0 = mash(" ");
        me.s1 = mash(" ");
        me.s2 = mash(" ");
        me.s0 -= mash(seed);
        if (me.s0 < 0) {
          me.s0 += 1;
        }
        me.s1 -= mash(seed);
        if (me.s1 < 0) {
          me.s1 += 1;
        }
        me.s2 -= mash(seed);
        if (me.s2 < 0) {
          me.s2 += 1;
        }
        mash = null;
      }
      function copy(f, t) {
        t.c = f.c;
        t.s0 = f.s0;
        t.s1 = f.s1;
        t.s2 = f.s2;
        return t;
      }
      function impl(seed, opts) {
        var xg = new Alea(seed), state = opts && opts.state, prng = xg.next;
        prng.int32 = function() {
          return xg.next() * 4294967296 | 0;
        };
        prng.double = function() {
          return prng() + (prng() * 2097152 | 0) * 11102230246251565e-32;
        };
        prng.quick = prng;
        if (state) {
          if (typeof state == "object") copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      function Mash() {
        var n = 4022871197;
        var mash = function(data) {
          data = String(data);
          for (var i = 0; i < data.length; i++) {
            n += data.charCodeAt(i);
            var h = 0.02519603282416938 * n;
            n = h >>> 0;
            h -= n;
            h *= n;
            n = h >>> 0;
            h -= n;
            n += h * 4294967296;
          }
          return (n >>> 0) * 23283064365386963e-26;
        };
        return mash;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.alea = impl;
      }
    })(
      exports,
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// node_modules/seedrandom/lib/xor128.js
var require_xor128 = __commonJS({
  "node_modules/seedrandom/lib/xor128.js"(exports, module) {
    (function(global, module2, define2) {
      function XorGen(seed) {
        var me = this, strseed = "";
        me.x = 0;
        me.y = 0;
        me.z = 0;
        me.w = 0;
        me.next = function() {
          var t = me.x ^ me.x << 11;
          me.x = me.y;
          me.y = me.z;
          me.z = me.w;
          return me.w ^= me.w >>> 19 ^ t ^ t >>> 8;
        };
        if (seed === (seed | 0)) {
          me.x = seed;
        } else {
          strseed += seed;
        }
        for (var k = 0; k < strseed.length + 64; k++) {
          me.x ^= strseed.charCodeAt(k) | 0;
          me.next();
        }
      }
      function copy(f, t) {
        t.x = f.x;
        t.y = f.y;
        t.z = f.z;
        t.w = f.w;
        return t;
      }
      function impl(seed, opts) {
        var xg = new XorGen(seed), state = opts && opts.state, prng = function() {
          return (xg.next() >>> 0) / 4294967296;
        };
        prng.double = function() {
          do {
            var top = xg.next() >>> 11, bot = (xg.next() >>> 0) / 4294967296, result = (top + bot) / (1 << 21);
          } while (result === 0);
          return result;
        };
        prng.int32 = xg.next;
        prng.quick = prng;
        if (state) {
          if (typeof state == "object") copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.xor128 = impl;
      }
    })(
      exports,
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// node_modules/seedrandom/lib/xorwow.js
var require_xorwow = __commonJS({
  "node_modules/seedrandom/lib/xorwow.js"(exports, module) {
    (function(global, module2, define2) {
      function XorGen(seed) {
        var me = this, strseed = "";
        me.next = function() {
          var t = me.x ^ me.x >>> 2;
          me.x = me.y;
          me.y = me.z;
          me.z = me.w;
          me.w = me.v;
          return (me.d = me.d + 362437 | 0) + (me.v = me.v ^ me.v << 4 ^ (t ^ t << 1)) | 0;
        };
        me.x = 0;
        me.y = 0;
        me.z = 0;
        me.w = 0;
        me.v = 0;
        if (seed === (seed | 0)) {
          me.x = seed;
        } else {
          strseed += seed;
        }
        for (var k = 0; k < strseed.length + 64; k++) {
          me.x ^= strseed.charCodeAt(k) | 0;
          if (k == strseed.length) {
            me.d = me.x << 10 ^ me.x >>> 4;
          }
          me.next();
        }
      }
      function copy(f, t) {
        t.x = f.x;
        t.y = f.y;
        t.z = f.z;
        t.w = f.w;
        t.v = f.v;
        t.d = f.d;
        return t;
      }
      function impl(seed, opts) {
        var xg = new XorGen(seed), state = opts && opts.state, prng = function() {
          return (xg.next() >>> 0) / 4294967296;
        };
        prng.double = function() {
          do {
            var top = xg.next() >>> 11, bot = (xg.next() >>> 0) / 4294967296, result = (top + bot) / (1 << 21);
          } while (result === 0);
          return result;
        };
        prng.int32 = xg.next;
        prng.quick = prng;
        if (state) {
          if (typeof state == "object") copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.xorwow = impl;
      }
    })(
      exports,
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// node_modules/seedrandom/lib/xorshift7.js
var require_xorshift7 = __commonJS({
  "node_modules/seedrandom/lib/xorshift7.js"(exports, module) {
    (function(global, module2, define2) {
      function XorGen(seed) {
        var me = this;
        me.next = function() {
          var X = me.x, i = me.i, t, v, w;
          t = X[i];
          t ^= t >>> 7;
          v = t ^ t << 24;
          t = X[i + 1 & 7];
          v ^= t ^ t >>> 10;
          t = X[i + 3 & 7];
          v ^= t ^ t >>> 3;
          t = X[i + 4 & 7];
          v ^= t ^ t << 7;
          t = X[i + 7 & 7];
          t = t ^ t << 13;
          v ^= t ^ t << 9;
          X[i] = v;
          me.i = i + 1 & 7;
          return v;
        };
        function init(me2, seed2) {
          var j, w, X = [];
          if (seed2 === (seed2 | 0)) {
            w = X[0] = seed2;
          } else {
            seed2 = "" + seed2;
            for (j = 0; j < seed2.length; ++j) {
              X[j & 7] = X[j & 7] << 15 ^ seed2.charCodeAt(j) + X[j + 1 & 7] << 13;
            }
          }
          while (X.length < 8) X.push(0);
          for (j = 0; j < 8 && X[j] === 0; ++j) ;
          if (j == 8) w = X[7] = -1;
          else w = X[j];
          me2.x = X;
          me2.i = 0;
          for (j = 256; j > 0; --j) {
            me2.next();
          }
        }
        init(me, seed);
      }
      function copy(f, t) {
        t.x = f.x.slice();
        t.i = f.i;
        return t;
      }
      function impl(seed, opts) {
        if (seed == null) seed = +/* @__PURE__ */ new Date();
        var xg = new XorGen(seed), state = opts && opts.state, prng = function() {
          return (xg.next() >>> 0) / 4294967296;
        };
        prng.double = function() {
          do {
            var top = xg.next() >>> 11, bot = (xg.next() >>> 0) / 4294967296, result = (top + bot) / (1 << 21);
          } while (result === 0);
          return result;
        };
        prng.int32 = xg.next;
        prng.quick = prng;
        if (state) {
          if (state.x) copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.xorshift7 = impl;
      }
    })(
      exports,
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// node_modules/seedrandom/lib/xor4096.js
var require_xor4096 = __commonJS({
  "node_modules/seedrandom/lib/xor4096.js"(exports, module) {
    (function(global, module2, define2) {
      function XorGen(seed) {
        var me = this;
        me.next = function() {
          var w = me.w, X = me.X, i = me.i, t, v;
          me.w = w = w + 1640531527 | 0;
          v = X[i + 34 & 127];
          t = X[i = i + 1 & 127];
          v ^= v << 13;
          t ^= t << 17;
          v ^= v >>> 15;
          t ^= t >>> 12;
          v = X[i] = v ^ t;
          me.i = i;
          return v + (w ^ w >>> 16) | 0;
        };
        function init(me2, seed2) {
          var t, v, i, j, w, X = [], limit = 128;
          if (seed2 === (seed2 | 0)) {
            v = seed2;
            seed2 = null;
          } else {
            seed2 = seed2 + "\0";
            v = 0;
            limit = Math.max(limit, seed2.length);
          }
          for (i = 0, j = -32; j < limit; ++j) {
            if (seed2) v ^= seed2.charCodeAt((j + 32) % seed2.length);
            if (j === 0) w = v;
            v ^= v << 10;
            v ^= v >>> 15;
            v ^= v << 4;
            v ^= v >>> 13;
            if (j >= 0) {
              w = w + 1640531527 | 0;
              t = X[j & 127] ^= v + w;
              i = 0 == t ? i + 1 : 0;
            }
          }
          if (i >= 128) {
            X[(seed2 && seed2.length || 0) & 127] = -1;
          }
          i = 127;
          for (j = 4 * 128; j > 0; --j) {
            v = X[i + 34 & 127];
            t = X[i = i + 1 & 127];
            v ^= v << 13;
            t ^= t << 17;
            v ^= v >>> 15;
            t ^= t >>> 12;
            X[i] = v ^ t;
          }
          me2.w = w;
          me2.X = X;
          me2.i = i;
        }
        init(me, seed);
      }
      function copy(f, t) {
        t.i = f.i;
        t.w = f.w;
        t.X = f.X.slice();
        return t;
      }
      ;
      function impl(seed, opts) {
        if (seed == null) seed = +/* @__PURE__ */ new Date();
        var xg = new XorGen(seed), state = opts && opts.state, prng = function() {
          return (xg.next() >>> 0) / 4294967296;
        };
        prng.double = function() {
          do {
            var top = xg.next() >>> 11, bot = (xg.next() >>> 0) / 4294967296, result = (top + bot) / (1 << 21);
          } while (result === 0);
          return result;
        };
        prng.int32 = xg.next;
        prng.quick = prng;
        if (state) {
          if (state.X) copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.xor4096 = impl;
      }
    })(
      exports,
      // window object or global
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// node_modules/seedrandom/lib/tychei.js
var require_tychei = __commonJS({
  "node_modules/seedrandom/lib/tychei.js"(exports, module) {
    (function(global, module2, define2) {
      function XorGen(seed) {
        var me = this, strseed = "";
        me.next = function() {
          var b = me.b, c = me.c, d = me.d, a = me.a;
          b = b << 25 ^ b >>> 7 ^ c;
          c = c - d | 0;
          d = d << 24 ^ d >>> 8 ^ a;
          a = a - b | 0;
          me.b = b = b << 20 ^ b >>> 12 ^ c;
          me.c = c = c - d | 0;
          me.d = d << 16 ^ c >>> 16 ^ a;
          return me.a = a - b | 0;
        };
        me.a = 0;
        me.b = 0;
        me.c = 2654435769 | 0;
        me.d = 1367130551;
        if (seed === Math.floor(seed)) {
          me.a = seed / 4294967296 | 0;
          me.b = seed | 0;
        } else {
          strseed += seed;
        }
        for (var k = 0; k < strseed.length + 20; k++) {
          me.b ^= strseed.charCodeAt(k) | 0;
          me.next();
        }
      }
      function copy(f, t) {
        t.a = f.a;
        t.b = f.b;
        t.c = f.c;
        t.d = f.d;
        return t;
      }
      ;
      function impl(seed, opts) {
        var xg = new XorGen(seed), state = opts && opts.state, prng = function() {
          return (xg.next() >>> 0) / 4294967296;
        };
        prng.double = function() {
          do {
            var top = xg.next() >>> 11, bot = (xg.next() >>> 0) / 4294967296, result = (top + bot) / (1 << 21);
          } while (result === 0);
          return result;
        };
        prng.int32 = xg.next;
        prng.quick = prng;
        if (state) {
          if (typeof state == "object") copy(state, xg);
          prng.state = function() {
            return copy(xg, {});
          };
        }
        return prng;
      }
      if (module2 && module2.exports) {
        module2.exports = impl;
      } else if (define2 && define2.amd) {
        define2(function() {
          return impl;
        });
      } else {
        this.tychei = impl;
      }
    })(
      exports,
      typeof module == "object" && module,
      // present in node.js
      typeof define == "function" && define
      // present with an AMD loader
    );
  }
});

// (disabled):crypto
var require_crypto = __commonJS({
  "(disabled):crypto"() {
  }
});

// node_modules/seedrandom/seedrandom.js
var require_seedrandom = __commonJS({
  "node_modules/seedrandom/seedrandom.js"(exports, module) {
    (function(global, pool, math) {
      var width = 256, chunks = 6, digits = 52, rngname = "random", startdenom = math.pow(width, chunks), significance = math.pow(2, digits), overflow = significance * 2, mask = width - 1, nodecrypto;
      function seedrandom(seed, options, callback) {
        var key = [];
        options = options == true ? { entropy: true } : options || {};
        var shortseed = mixkey(flatten(
          options.entropy ? [seed, tostring(pool)] : seed == null ? autoseed() : seed,
          3
        ), key);
        var arc4 = new ARC4(key);
        var prng = function() {
          var n = arc4.g(chunks), d = startdenom, x = 0;
          while (n < significance) {
            n = (n + x) * width;
            d *= width;
            x = arc4.g(1);
          }
          while (n >= overflow) {
            n /= 2;
            d /= 2;
            x >>>= 1;
          }
          return (n + x) / d;
        };
        prng.int32 = function() {
          return arc4.g(4) | 0;
        };
        prng.quick = function() {
          return arc4.g(4) / 4294967296;
        };
        prng.double = prng;
        mixkey(tostring(arc4.S), pool);
        return (options.pass || callback || function(prng2, seed2, is_math_call, state) {
          if (state) {
            if (state.S) {
              copy(state, arc4);
            }
            prng2.state = function() {
              return copy(arc4, {});
            };
          }
          if (is_math_call) {
            math[rngname] = prng2;
            return seed2;
          } else return prng2;
        })(
          prng,
          shortseed,
          "global" in options ? options.global : this == math,
          options.state
        );
      }
      function ARC4(key) {
        var t, keylen = key.length, me = this, i = 0, j = me.i = me.j = 0, s = me.S = [];
        if (!keylen) {
          key = [keylen++];
        }
        while (i < width) {
          s[i] = i++;
        }
        for (i = 0; i < width; i++) {
          s[i] = s[j = mask & j + key[i % keylen] + (t = s[i])];
          s[j] = t;
        }
        (me.g = function(count) {
          var t2, r = 0, i2 = me.i, j2 = me.j, s2 = me.S;
          while (count--) {
            t2 = s2[i2 = mask & i2 + 1];
            r = r * width + s2[mask & (s2[i2] = s2[j2 = mask & j2 + t2]) + (s2[j2] = t2)];
          }
          me.i = i2;
          me.j = j2;
          return r;
        })(width);
      }
      function copy(f, t) {
        t.i = f.i;
        t.j = f.j;
        t.S = f.S.slice();
        return t;
      }
      ;
      function flatten(obj, depth) {
        var result = [], typ = typeof obj, prop;
        if (depth && typ == "object") {
          for (prop in obj) {
            try {
              result.push(flatten(obj[prop], depth - 1));
            } catch (e) {
            }
          }
        }
        return result.length ? result : typ == "string" ? obj : obj + "\0";
      }
      function mixkey(seed, key) {
        var stringseed = seed + "", smear, j = 0;
        while (j < stringseed.length) {
          key[mask & j] = mask & (smear ^= key[mask & j] * 19) + stringseed.charCodeAt(j++);
        }
        return tostring(key);
      }
      function autoseed() {
        try {
          var out;
          if (nodecrypto && (out = nodecrypto.randomBytes)) {
            out = out(width);
          } else {
            out = new Uint8Array(width);
            (global.crypto || global.msCrypto).getRandomValues(out);
          }
          return tostring(out);
        } catch (e) {
          var browser = global.navigator, plugins = browser && browser.plugins;
          return [+/* @__PURE__ */ new Date(), global, plugins, global.screen, tostring(pool)];
        }
      }
      function tostring(a) {
        return String.fromCharCode.apply(0, a);
      }
      mixkey(math.random(), pool);
      if (typeof module == "object" && module.exports) {
        module.exports = seedrandom;
        try {
          nodecrypto = require_crypto();
        } catch (ex) {
        }
      } else if (typeof define == "function" && define.amd) {
        define(function() {
          return seedrandom;
        });
      } else {
        math["seed" + rngname] = seedrandom;
      }
    })(
      // global: `self` in browsers (including strict mode and web workers),
      // otherwise `this` in Node and other environments
      typeof self !== "undefined" ? self : exports,
      [],
      // pool: entropy pool starts empty
      Math
      // math: package containing random, pow, and seedrandom
    );
  }
});

// node_modules/seedrandom/index.js
var require_seedrandom2 = __commonJS({
  "node_modules/seedrandom/index.js"(exports, module) {
    var alea = require_alea();
    var xor128 = require_xor128();
    var xorwow = require_xorwow();
    var xorshift7 = require_xorshift7();
    var xor4096 = require_xor4096();
    var tychei = require_tychei();
    var sr = require_seedrandom();
    sr.alea = alea;
    sr.xor128 = xor128;
    sr.xorwow = xorwow;
    sr.xorshift7 = xorshift7;
    sr.xor4096 = xor4096;
    sr.tychei = tychei;
    module.exports = sr;
  }
});

// node_modules/6502.ts/lib/tools/rng/SeedrandomGenerator.js
var require_SeedrandomGenerator = __commonJS({
  "node_modules/6502.ts/lib/tools/rng/SeedrandomGenerator.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var SeedrandomGenerator = class {
      constructor(_rng) {
        this._rng = _rng;
      }
      single() {
        return this._rng.quick();
      }
      double() {
        return this._rng.double();
      }
      int32() {
        return this._rng.int32();
      }
      int(max) {
        return (this._rng.int32() >>> 0) % (max + 1);
      }
      saveState() {
        return this._rng.state();
      }
    };
    exports.default = SeedrandomGenerator;
  }
});

// node_modules/6502.ts/lib/tools/rng/factory.js
var require_factory = __commonJS({
  "node_modules/6502.ts/lib/tools/rng/factory.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.restoreRng = exports.createRng = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var seedrandom = tslib_1.__importStar(require_seedrandom2());
    var SeedrandomGenerator_1 = tslib_1.__importDefault(require_SeedrandomGenerator());
    function createRng(seed) {
      if (seed < 0) {
        seed = Math.random();
      }
      return new SeedrandomGenerator_1.default(seedrandom.alea(seed, {
        state: true
      }));
    }
    exports.createRng = createRng;
    function restoreRng(state) {
      return new SeedrandomGenerator_1.default(seedrandom.alea("", {
        state
      }));
    }
    exports.restoreRng = restoreRng;
  }
});

// node_modules/6502.ts/lib/machine/stella/Board.js
var require_Board = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/Board.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var BoardInterface_1 = tslib_1.__importDefault(require_BoardInterface());
    var Bus_1 = tslib_1.__importDefault(require_Bus());
    var Pia_1 = tslib_1.__importDefault(require_Pia());
    var Tia_1 = tslib_1.__importDefault(require_Tia());
    var Config_1 = tslib_1.__importDefault(require_Config());
    var ControlPanel_1 = tslib_1.__importDefault(require_ControlPanel());
    var DigitalJoystick_1 = tslib_1.__importDefault(require_DigitalJoystick());
    var Paddle_1 = tslib_1.__importDefault(require_Paddle());
    var factory_1 = require_factory();
    var Factory_1 = tslib_1.__importDefault(require_Factory());
    var Board2 = class _Board {
      constructor(_config, cartridge, cpuFactory) {
        this._config = _config;
        this.trap = new microevent_ts_1.Event();
        this.clock = new microevent_ts_1.Event();
        this.cpuClock = new microevent_ts_1.Event();
        this.systemReset = new microevent_ts_1.Event();
        this._clockMode = 1;
        this._cpuCycles = 0;
        this._trap = false;
        this._audioEnabled = true;
        this._suspended = true;
        this._subClock = 0;
        this._clockHz = 0;
        this._sliceSize = 0;
        this._timer = {
          tick: (clocks) => this.tick(clocks),
          start: (scheduler) => this._start(scheduler),
          stop: () => this._stop(),
          isRunning: () => !!this._runTask
        };
        this._rng = (0, factory_1.createRng)(_config.randomSeed < 0 ? Math.random() : _config.randomSeed);
        cartridge.randomize(this._rng);
        const bus = new Bus_1.default();
        if (typeof cpuFactory === "undefined") {
          cpuFactory = (_bus, rng) => new Factory_1.default(_config.cpuType).create(_bus, rng);
        }
        const controlPanel = new ControlPanel_1.default(), joystick0 = new DigitalJoystick_1.default(), joystick1 = new DigitalJoystick_1.default(), paddles = new Array(4);
        for (let i = 0; i < 4; i++) {
          paddles[i] = new Paddle_1.default();
        }
        const cpu = cpuFactory(bus, this._rng);
        const pia = new Pia_1.default(controlPanel, joystick0, joystick1, this._rng);
        const tia = new Tia_1.default(_config, joystick0, joystick1, paddles);
        cpu.setInvalidInstructionCallback(() => this._onInvalidInstruction());
        tia.setCpu(cpu).setBus(bus).setCpuTimeProvider(() => this.getCpuTime());
        cartridge.setCpu(cpu).setBus(bus).setCpuTimeProvider(() => this.getCpuTime()).setRng(this._rng);
        pia.setBus(bus);
        bus.setTia(tia).setPia(pia).setCartridge(cartridge);
        this._bus = bus;
        this._cpu = cpu;
        this._tia = tia;
        this._pia = pia;
        this._cartridge = cartridge;
        this._controlPanel = controlPanel;
        this._joystick0 = joystick0;
        this._joystick1 = joystick1;
        this._paddles = paddles;
        this._bus.event.trap.addHandler((payload) => this.triggerTrap(1, payload.message));
        this._clockHz = Config_1.default.getClockHz(_config);
        this._sliceSize = 228 * (_config.tvMode === 0 ? 262 : 312);
        this.reset();
      }
      getCpu() {
        return this._cpu;
      }
      getBus() {
        return this._bus;
      }
      getVideoOutput() {
        return this._tia;
      }
      getWaveformChannels() {
        return [0, 1].map((i) => this._tia.getWaveformChannel(i));
      }
      getPCMChannel() {
        return this._tia.getPCMChannel();
      }
      getTimer() {
        return this._timer;
      }
      getConfig() {
        return this._config;
      }
      reset() {
        this._cpu.reset();
        this._tia.reset();
        this._pia.reset();
        this._cartridge.reset();
        this._controlPanel.getResetButton().toggle(false);
        this._controlPanel.getSelectSwitch().toggle(false);
        this._controlPanel.getColorSwitch().toggle(false);
        this._controlPanel.getDifficultySwitchP0().toggle(true);
        this._controlPanel.getDifficultySwitchP1().toggle(true);
        this._subClock = 0;
        this._cpuCycles = 0;
        this.systemReset.dispatch();
        return this;
      }
      boot() {
        let cycles = 0, cpuCycles = 0;
        this.reset();
        if (this._cpu.executionState !== 0) {
          throw new Error("Already booted!");
        }
        while (this._cpu.executionState !== 1) {
          this._cycle();
          cycles++;
          if (this._subClock === 0) {
            cpuCycles++;
          }
        }
        this.cpuClock.dispatch(cpuCycles);
        this.clock.dispatch(cycles);
        return this;
      }
      suspend() {
        this._suspended = true;
        this._updateAudioState();
      }
      resume() {
        this._suspended = false;
        this._updateAudioState();
      }
      setAudioEnabled(state) {
        this._audioEnabled = state;
        this._updateAudioState();
      }
      triggerTrap(reason, message) {
        this._stop();
        this._trap = true;
        if (this.trap.hasHandlers) {
          this.trap.dispatch(new BoardInterface_1.default.TrapPayload(reason, this, message));
        } else {
          throw new Error(message);
        }
        return this;
      }
      getControlPanel() {
        return this._controlPanel;
      }
      getJoystick0() {
        return this._joystick0;
      }
      getJoystick1() {
        return this._joystick1;
      }
      getBoardStateDebug() {
        const sep = "============";
        return "TIA:\n" + sep + "\n" + this._tia.getDebugState() + `

PIA:
${sep}
${this._pia.getDebugState()}
`;
      }
      setClockMode(clockMode) {
        this._clockMode = clockMode;
        return this;
      }
      getClockMode() {
        return this._clockMode;
      }
      getPaddle(idx) {
        return this._paddles[idx];
      }
      getCpuTime() {
        return this._cpuCycles / Config_1.default.getClockHz(this._config) * 3;
      }
      tick(requestedCycles) {
        let i = 0, cycles = 0, cpuCycles = 0, lastExecutionState = this._cpu.executionState;
        this._trap = false;
        while (i++ < requestedCycles && !this._trap) {
          this._cycle();
          cycles++;
          if (this._subClock === 0) {
            cpuCycles++;
            this._cpuCycles++;
          }
          if (lastExecutionState !== this._cpu.executionState) {
            lastExecutionState = this._cpu.executionState;
            if (this._cpu.executionState === 1) {
              this._cartridge.notifyCpuCycleComplete();
              if (this._clockMode === 0 && cpuCycles > 0 && this.cpuClock.hasHandlers) {
                this.cpuClock.dispatch(cpuCycles);
                cpuCycles = 0;
              }
            }
          }
        }
        if (cpuCycles > 0 && this.cpuClock.hasHandlers) {
          this.cpuClock.dispatch(cpuCycles);
        }
        if (cycles > 0 && this.clock.hasHandlers) {
          this.clock.dispatch(cycles);
        }
        return cycles;
      }
      getSubclock() {
        return this._subClock;
      }
      static _executeSlice(board, _timeSlice) {
        const slice = _timeSlice ? Math.round(_timeSlice * board._clockHz / 1e3) : board._sliceSize;
        return board.tick(slice) / board._clockHz * 1e3;
      }
      _updateAudioState() {
        this._tia.setAudioEnabled(this._audioEnabled && !this._suspended);
      }
      _cycle() {
        this._tia.cycle();
        if (this._subClock++ >= 2) {
          this._pia.cycle();
          this._cpu.cycle();
          this._subClock = 0;
        }
      }
      _start(scheduler) {
        if (this._runTask) {
          return;
        }
        this._runTask = scheduler.start(_Board._executeSlice, this, 1e3 / (this._config.tvMode === 0 ? 60 : 50));
      }
      _stop() {
        if (!this._runTask) {
          return;
        }
        this._runTask.stop();
        this._runTask = void 0;
      }
      _onInvalidInstruction() {
        this.triggerTrap(0, "invalid instruction");
      }
    };
    exports.default = Board2;
  }
});

// node_modules/6502.ts/lib/machine/stella/cartridge/CartridgeInterface.js
var require_CartridgeInterface = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/cartridge/CartridgeInterface.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var CartridgeInterface;
    (function(CartridgeInterface2) {
      class TrapPayload {
        constructor(reason, cartridge, message) {
          this.reason = reason;
          this.cartridge = cartridge;
          this.message = message;
        }
      }
      CartridgeInterface2.TrapPayload = TrapPayload;
    })(CartridgeInterface || (CartridgeInterface = {}));
    exports.default = CartridgeInterface;
  }
});

// node_modules/6502.ts/lib/machine/stella/cartridge/CartridgeInfo.js
var require_CartridgeInfo = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/cartridge/CartridgeInfo.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var CartridgeInfo;
    (function(CartridgeInfo2) {
      let CartridgeType;
      (function(CartridgeType2) {
        CartridgeType2["vanilla_2k"] = "vanilla_2k";
        CartridgeType2["vanilla_4k"] = "vanilla_4k";
        CartridgeType2["bankswitch_2k_cv"] = "bankswitch_2k_cv";
        CartridgeType2["bankswitch_8k_F8"] = "bankswitch_8k_F8";
        CartridgeType2["bankswitch_8k_E0"] = "bankswitch_8k_E0";
        CartridgeType2["bankswitch_8k_3F"] = "bankswitch_8k_3F";
        CartridgeType2["bankswitch_8k_FE"] = "bankswitch_8k_FE";
        CartridgeType2["bankswitch_8k_UA"] = "bankswitch_8k_UA";
        CartridgeType2["bankswitch_8k_DPC"] = "bankswitch_8k_DPC";
        CartridgeType2["bankswitch_8k_econobanking"] = "bankswitch_8k_econobanking";
        CartridgeType2["bankswitch_8k_pp"] = "bankswitch_8k_pp";
        CartridgeType2["bankswitch_12k_FA"] = "bankswitch_12k_FA";
        CartridgeType2["bankswitch_16k_F6"] = "bankswitch_16k_F6";
        CartridgeType2["bankswitch_16k_E7"] = "bankswitch_16k_E7";
        CartridgeType2["bankswitch_FA2"] = "bankswitch_FA2";
        CartridgeType2["bankswitch_32k_F4"] = "bankswitch_32k_F4";
        CartridgeType2["bankswitch_64k_F0"] = "bankswitch_64k_F0";
        CartridgeType2["bankswitch_64k_EF"] = "bankswitch_64k_EF";
        CartridgeType2["bankswitch_3E"] = "bankswitch_3E";
        CartridgeType2["bankswitch_supercharger"] = "bankswitch_supercharger";
        CartridgeType2["bankswitch_dpc_plus"] = "bankswitch_dpc_plus";
        CartridgeType2["bankswitch_cdf"] = "bankswitch_cdf";
        CartridgeType2["unknown"] = "unknown";
      })(CartridgeType = CartridgeInfo2.CartridgeType || (CartridgeInfo2.CartridgeType = {}));
      function getAllTypes() {
        return [
          CartridgeType.vanilla_2k,
          CartridgeType.vanilla_4k,
          CartridgeType.bankswitch_2k_cv,
          CartridgeType.bankswitch_8k_F8,
          CartridgeType.bankswitch_8k_E0,
          CartridgeType.bankswitch_8k_3F,
          CartridgeType.bankswitch_8k_FE,
          CartridgeType.bankswitch_8k_UA,
          CartridgeType.bankswitch_8k_econobanking,
          CartridgeType.bankswitch_8k_pp,
          CartridgeType.bankswitch_12k_FA,
          CartridgeType.bankswitch_8k_DPC,
          CartridgeType.bankswitch_16k_F6,
          CartridgeType.bankswitch_16k_E7,
          CartridgeType.bankswitch_FA2,
          CartridgeType.bankswitch_32k_F4,
          CartridgeType.bankswitch_3E,
          CartridgeType.bankswitch_64k_F0,
          CartridgeType.bankswitch_64k_EF,
          CartridgeType.bankswitch_supercharger,
          CartridgeType.bankswitch_dpc_plus,
          CartridgeType.bankswitch_cdf,
          CartridgeType.unknown
        ];
      }
      CartridgeInfo2.getAllTypes = getAllTypes;
      function describeCartridgeType(cartridgeType) {
        switch (cartridgeType) {
          case CartridgeType.vanilla_2k:
            return "plain 2k";
          case CartridgeType.vanilla_4k:
            return "plain 4k";
          case CartridgeType.bankswitch_2k_cv:
            return "2k CommaVideo scheme";
          case CartridgeType.bankswitch_8k_F8:
            return "bankswitched 8k, F8 (Atari) scheme";
          case CartridgeType.bankswitch_8k_E0:
            return "bankswitched 8k, E0 (Parker Bros.) scheme";
          case CartridgeType.bankswitch_8k_3F:
            return "bankswitched 8k, 3F (Tigervision) scheme";
          case CartridgeType.bankswitch_8k_FE:
            return "bankswitched 8k, FE (Activision) scheme";
          case CartridgeType.bankswitch_8k_UA:
            return "bankswitched 8k, UA (Pleiades) scheme";
          case CartridgeType.bankswitch_8k_pp:
            return "bankswitched 8k, Pink Panther scheme";
          case CartridgeType.bankswitch_12k_FA:
            return "bankswitched 12k, FA (CBS) scheme";
          case CartridgeType.bankswitch_8k_DPC:
            return "bankswitched 8k + DPC";
          case CartridgeType.bankswitch_8k_econobanking:
            return "bankswitched 8k, econobanking scheme";
          case CartridgeType.bankswitch_16k_F6:
            return "bankswitched 16k, F6 (Atari) scheme";
          case CartridgeType.bankswitch_16k_E7:
            return "bankswitched 16k, E7 (M-Network) scheme";
          case CartridgeType.bankswitch_FA2:
            return "bankswitched 28k/29k, FA2 (modified CBS) scheme";
          case CartridgeType.bankswitch_32k_F4:
            return "bankswitched 32k, F4 (Atari) scheme";
          case CartridgeType.bankswitch_3E:
            return "bankswitched 3E (Tigervision + RAM) scheme";
          case CartridgeType.bankswitch_64k_F0:
            return "bankswitched 64k, F0 (Megaboy) scheme";
          case CartridgeType.bankswitch_64k_EF:
            return "bankswitched 64k, EFSC (Homestar Runner) scheme";
          case CartridgeType.bankswitch_supercharger:
            return "bankswitched supercharger";
          case CartridgeType.bankswitch_dpc_plus:
            return "bankswitched DPC+";
          case CartridgeType.bankswitch_cdf:
            return "bankswitched CDF";
          case CartridgeType.unknown:
            return "unknown";
        }
      }
      CartridgeInfo2.describeCartridgeType = describeCartridgeType;
    })(CartridgeInfo || (CartridgeInfo = {}));
    exports.default = CartridgeInfo;
  }
});

// node_modules/6502.ts/lib/machine/stella/cartridge/AbstractCartridge.js
var require_AbstractCartridge = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/cartridge/AbstractCartridge.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var microevent_ts_1 = require_lib();
    var CartridgeInterface_1 = tslib_1.__importDefault(require_CartridgeInterface());
    var CartridgeInfo_1 = tslib_1.__importDefault(require_CartridgeInfo());
    var AbstractCartridge = class {
      constructor() {
        this.trap = new microevent_ts_1.Event();
      }
      init() {
        return tslib_1.__awaiter(this, void 0, void 0, function* () {
        });
      }
      reset() {
      }
      read(address) {
        return 0;
      }
      peek(address) {
        return this.read(address);
      }
      write(address, value) {
      }
      getType() {
        return CartridgeInfo_1.default.CartridgeType.unknown;
      }
      setCpu(cpu) {
        return this;
      }
      setBus(bus) {
        return this;
      }
      setRng(rng) {
        return this;
      }
      setCpuTimeProvider(provider) {
        return this;
      }
      notifyCpuCycleComplete() {
      }
      randomize(rng) {
      }
      triggerTrap(reason, message) {
        if (this.trap.hasHandlers) {
          this.trap.dispatch(new CartridgeInterface_1.default.TrapPayload(reason, this, message));
        } else {
          throw new Error(message);
        }
      }
    };
    exports.default = AbstractCartridge;
  }
});

// node_modules/6502.ts/lib/machine/stella/cartridge/Cartridge2k.js
var require_Cartridge2k = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/cartridge/Cartridge2k.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var AbstractCartridge_1 = tslib_1.__importDefault(require_AbstractCartridge());
    var CartridgeInfo_1 = tslib_1.__importDefault(require_CartridgeInfo());
    function nextPowerOfTwo(x) {
      let v = 1;
      while (v < x) {
        v *= 2;
      }
      return v;
    }
    function padBuffer(buffer) {
      const paddedLength = nextPowerOfTwo(buffer.length);
      if (paddedLength === buffer.length) {
        return buffer;
      }
      const paddedBuffer = new Uint8Array(paddedLength);
      for (let i = 0; i < paddedLength; i++) {
        paddedBuffer[paddedLength - i - 1] = i < buffer.length ? buffer[buffer.length - i - 1] : 0;
      }
      return paddedBuffer;
    }
    var Cartridge2k2 = class extends AbstractCartridge_1.default {
      constructor(buffer) {
        super();
        this._rom = new Uint8Array(2048);
        if (buffer.length > 2048) {
          throw new Error(`buffer is not a 2k cartridge image: wrong length ${buffer.length}`);
        }
        const paddedBuffer = padBuffer(buffer);
        for (let i = 0; i < 2048; i++) {
          this._rom[i] = buffer[i % paddedBuffer.length];
        }
      }
      read(address) {
        return this._rom[address & 2047];
      }
      getType() {
        return CartridgeInfo_1.default.CartridgeType.vanilla_2k;
      }
    };
    exports.default = Cartridge2k2;
  }
});

// node_modules/6502.ts/lib/machine/stella/cartridge/Cartridge4k.js
var require_Cartridge4k = __commonJS({
  "node_modules/6502.ts/lib/machine/stella/cartridge/Cartridge4k.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var tslib_1 = (init_tslib_es6(), __toCommonJS(tslib_es6_exports));
    var AbstractCartridge_1 = tslib_1.__importDefault(require_AbstractCartridge());
    var CartridgeInfo_1 = tslib_1.__importDefault(require_CartridgeInfo());
    var Cartridge4k2 = class extends AbstractCartridge_1.default {
      constructor(buffer) {
        super();
        this._rom = new Uint8Array(4096);
        if (buffer.length !== 4096) {
          console.warn(`buffer has invalid size for 4K image: ${buffer.length} bytes`);
        }
        const len = Math.min(4096, buffer.length);
        for (let i = 0; i < 4096 && i < buffer.length; i++) {
          this._rom[4095 - i] = buffer[len - 1 - i];
        }
      }
      read(address) {
        return this._rom[address & 4095];
      }
      getType() {
        return CartridgeInfo_1.default.CartridgeType.vanilla_4k;
      }
    };
    exports.default = Cartridge4k2;
  }
});

// node_modules/6502.ts/lib/video/surface/ArrayBufferSurface.js
var require_ArrayBufferSurface = __commonJS({
  "node_modules/6502.ts/lib/video/surface/ArrayBufferSurface.js"(exports) {
    "use strict";
    Object.defineProperty(exports, "__esModule", { value: true });
    exports.default = void 0;
    var ArrayBufferSurface2 = class _ArrayBufferSurface {
      constructor() {
        this._height = 0;
        this._width = 0;
        this._buffer = null;
      }
      static createFromArrayBuffer(width, height, buffer) {
        return new _ArrayBufferSurface().replaceUnderlyingBuffer(width, height, buffer);
      }
      replaceUnderlyingBuffer(width, height, buffer) {
        if (width * height * 4 !== buffer.byteLength) {
          throw new Error("surface size mismatch");
        }
        this._width = width;
        this._height = height;
        this._underlyingBuffer = buffer;
        this._buffer = new Uint32Array(this._underlyingBuffer);
        return this;
      }
      getUnderlyingBuffer() {
        return this._underlyingBuffer;
      }
      resetUnderlyingBuffer() {
        this._width = this._height = 0;
        this._underlyingBuffer = this._buffer = null;
        return this;
      }
      getWidth() {
        return this._width;
      }
      getHeight() {
        return this._height;
      }
      getBuffer() {
        return this._buffer;
      }
      getByteOrder() {
        return 0;
      }
      fill(value) {
        for (let i = 0; i < this._buffer.length; i++) {
          this._buffer[i] = value;
        }
        return this;
      }
    };
    exports.default = ArrayBufferSurface2;
  }
});

// ale.js
var import_Board = __toESM(require_Board());
var import_Config = __toESM(require_Config());
var import_Cartridge2k = __toESM(require_Cartridge2k());
var import_Cartridge4k = __toESM(require_Cartridge4k());
var import_ArrayBufferSurface = __toESM(require_ArrayBufferSurface());
var WIDTH = 160;
var HEIGHT = 210;
var SURFACE_HEIGHT = 212;
var CLOCKS_PER_LINE = 228;
var LINES_PER_FRAME = 262;
var ACTION_SWITCHES = {
  NOOP: [],
  FIRE: ["fire"],
  UP: ["up"],
  RIGHT: ["right"],
  LEFT: ["left"],
  DOWN: ["down"],
  UPRIGHT: ["up", "right"],
  UPLEFT: ["up", "left"],
  DOWNRIGHT: ["down", "right"],
  DOWNLEFT: ["down", "left"],
  UPFIRE: ["up", "fire"],
  RIGHTFIRE: ["right", "fire"],
  LEFTFIRE: ["left", "fire"],
  DOWNFIRE: ["down", "fire"]
};
var ram = (bytes, offset) => bytes[offset & 127];
var bcd = (v) => 10 * (v >> 4) + (v & 15);
var decimal2 = (bytes, lower, higher) => bcd(ram(bytes, lower)) + (higher < 0 ? 0 : 100 * bcd(ram(bytes, higher)));
var decimal3 = (bytes, lower, middle, higher) => decimal2(bytes, lower, middle) + 1e4 * bcd(ram(bytes, higher));
var GAMES = {
  Freeway: {
    rom: "roms/freeway.bin",
    md5: "8e0ab801b1705a740b476b7f588c6d16",
    actions: ["NOOP", "UP", "DOWN"],
    // ALE presses RESET once for the reset and once more when it applies game mode 0.
    resetPresses: 2,
    reset: () => ({ score: 0 }),
    step(bytes, s) {
      const score = decimal2(bytes, 103, -1);
      const reward = Math.min(1, Math.max(0, score - s.score));
      s.score = score;
      return { reward, terminal: ram(bytes, 22) === 1 };
    }
  },
  Atlantis: {
    rom: "roms/atlantis.bin",
    md5: "9ad36e699ef6f45d9eb6c4cf90475c9f",
    actions: ["NOOP", "FIRE", "RIGHTFIRE", "LEFTFIRE"],
    resetPresses: 1,
    reset: () => ({ score: 0, lives: 6 }),
    step(bytes, s) {
      const score = decimal3(bytes, 162, 163, 161) * 100;
      let reward = score - s.score;
      const old = s.score;
      s.score = score;
      s.lives = ram(bytes, 241);
      const terminal = s.lives === 255;
      if (terminal) {
        reward = 0;
        s.score = old;
      }
      return { reward, terminal };
    }
  }
};
var Environment = class {
  constructor(game, romBytes, { seed = 0, frameskip = 4, maxFrames = 108e3 } = {}) {
    if (!GAMES[game]) throw new Error(`no game ${game}`);
    this.game = game;
    this.settings = GAMES[game];
    this.actions = this.settings.actions;
    this.frameskip = frameskip;
    this.maxFrames = maxFrames;
    const bytes = romBytes instanceof Uint8Array ? romBytes : new Uint8Array(romBytes);
    const cartridge = bytes.length <= 2048 ? new import_Cartridge2k.default(bytes) : new import_Cartridge4k.default(bytes);
    const config = import_Config.default.create({ tvMode: 0, enableAudio: false, randomSeed: seed, emulatePaddles: false });
    this.board = new import_Board.default(config, cartridge);
    this.surface = import_ArrayBufferSurface.default.createFromArrayBuffer(WIDTH, SURFACE_HEIGHT, new ArrayBuffer(WIDTH * SURFACE_HEIGHT * 4));
    this.pixels = new Uint8Array(this.surface.getUnderlyingBuffer());
    this.frameReady = false;
    const video = this.board.getVideoOutput();
    video.setSurfaceFactory(() => this.surface);
    video.newFrame.addHandler(() => {
      this.frameReady = true;
    });
    this.bus = this.board.getBus();
    this.joystick = this.board.getJoystick0();
    this.panel = this.board.getControlPanel();
    this.ramBytes = new Uint8Array(128);
    this.episodeFrames = 0;
    this.frames = 0;
    this.state = this.settings.reset();
    this.terminal = false;
    this.booted = false;
  }
  _frame() {
    this.frameReady = false;
    let guard = 0;
    while (!this.frameReady && guard++ < 2 * LINES_PER_FRAME) this.board.tick(CLOCKS_PER_LINE);
    if (!this.frameReady) throw new Error("the emulator produced no frame");
    this.frames++;
  }
  _apply(action) {
    const names = ACTION_SWITCHES[this.actions[action]];
    for (const name of ["up", "down", "left", "right", "fire"]) {
      const sw = name === "fire" ? this.joystick.getFire() : this.joystick[`get${name[0].toUpperCase()}${name.slice(1)}`]();
      sw.toggle(names.includes(name));
    }
  }
  readRam() {
    for (let i = 0; i < 128; i++) this.ramBytes[i] = this.bus.peek(128 + i);
    return this.ramBytes;
  }
  // ALE's reset: a console reset, 60 idle frames, RESET held for four frames (per press), then the game's own reset.
  reset() {
    if (this.booted) this.board.reset();
    else {
      this.board.boot();
      this.booted = true;
    }
    this.panel.getDifficultySwitchP0().toggle(true);
    this.panel.getDifficultySwitchP1().toggle(true);
    this.panel.getColorSwitch().toggle(false);
    this.panel.getSelectSwitch().toggle(false);
    this.panel.getResetButton().toggle(false);
    this._apply(0);
    for (let i = 0; i < 60; i++) this._frame();
    for (let press = 0; press < this.settings.resetPresses; press++) {
      this.panel.getResetButton().toggle(true);
      for (let i = 0; i < 4; i++) this._frame();
      this.panel.getResetButton().toggle(false);
    }
    this.state = this.settings.reset();
    this.terminal = false;
    this.episodeFrames = 0;
    this.settings.step(this.readRam(), this.state);
    return this.screen();
  }
  // One agent step: the action held for `frameskip` frames, rewards summed, the game rules read after every frame.
  step(action) {
    if (!Number.isInteger(action) || action < 0 || action >= this.actions.length) throw new Error(`invalid action ${action}`);
    this._apply(action);
    let reward = 0;
    for (let i = 0; i < this.frameskip; i++) {
      if (this.terminal || this.episodeFrames >= this.maxFrames) break;
      this._frame();
      this.episodeFrames++;
      const r = this.settings.step(this.readRam(), this.state);
      reward += r.reward;
      this.terminal = r.terminal;
    }
    const truncated = !this.terminal && this.episodeFrames >= this.maxFrames;
    return { reward, terminal: this.terminal, truncated, score: this.state.score };
  }
  // The last frame as RGBA bytes, 160 x 210 (the ALE screen); the core renders 212 lines.
  screen() {
    return this.pixels.subarray(0, WIDTH * HEIGHT * 4);
  }
};
export {
  Environment,
  GAMES,
  HEIGHT,
  SURFACE_HEIGHT,
  WIDTH
};
