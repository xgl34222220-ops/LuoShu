// LuoShu native font: logging. Only used when the user turned verbose logging on.
#pragma once

#if defined(__ANDROID__)
#include <android/log.h>
#define LSNF_LOG_TAG "LuoShuNativeFont"
#define LSNF_LOGI(...) __android_log_print(ANDROID_LOG_INFO, LSNF_LOG_TAG, __VA_ARGS__)
#define LSNF_LOGW(...) __android_log_print(ANDROID_LOG_WARN, LSNF_LOG_TAG, __VA_ARGS__)
#else
#define LSNF_LOGI(...) ((void)0)
#define LSNF_LOGW(...) ((void)0)
#endif
