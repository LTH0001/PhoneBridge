package com.phonebridge.app;
public class HardwareNamesTest {
    public static void main(String[] args){
        check("Core Ultra 7 265K",HardwareNames.compact("Intel(R) Core(TM) Ultra 7 265K","未知"));
        check("RTX 2080 Ti",HardwareNames.compact("NVIDIA GeForce RTX 2080 Ti","未知"));
        check("未知",HardwareNames.compact("CPU","未知"));
        check("未知",HardwareNames.compact(null,"未知"));
        System.out.println("HardwareNames: 4 checks passed");
    }
    private static void check(String expected,String actual){if(!expected.equals(actual))throw new AssertionError(actual);}
}
